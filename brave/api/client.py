# encoding: utf-8

from __future__ import unicode_literals

import requests

from binascii import hexlify, unhexlify
from datetime import datetime
from webob import Response
from marrow.util.bunch import Bunch
from requests.auth import AuthBase


log = __import__('logging').getLogger(__name__)


class SignedAuth(AuthBase):
    def __init__(self, identity, private, public):
        self.identity = identity
        self.private = private
        self.public = public
    
    def __call__(self, request):
        request.headers['Date'] = Response(date=datetime.utcnow()).headers['Date']
        request.headers['X-Service'] = self.identity
        
        if request.body is None:
            request.body = ''
        
        canon = "{r.headers[date]}\n{r.url}\n{r.body}".format(r=request)
        log.debug("Canonical request:\n\n\"{0}\"".format(canon))
        request.headers['X-Signature'] = hexlify(self.private.sign(canon))
        
        request.register_hook('response', self.validate)
        
        return request
    
    def validate(self, response, *args, **kw):
        if response.status_code != requests.codes.ok:
            log.debug("Skipping validation of non-200 response.")
            return
        
        log.info("Validating %s request signature: %s", self.identity, response.headers['X-Signature'])
        canon = "{ident}\n{r.headers[Date]}\n{r.url}\n{r.content}".format(ident=self.identity, r=response)
        log.debug("Canonical data:\n%r", canon)
        
        # Raises an exception on failure.
        self.public.verify(unhexlify(response.headers['X-Signature']), canon)


class API(object):
    __slots__ = ('endpoint', 'identity', 'private', 'public', 'pool')
    
    def __init__(self, endpoint, identity, private, public, pool=None):
        self.endpoint = unicode(endpoint)
        self.identity = identity
        self.private = private
        self.public = public
        
        if not pool:
            self.pool = requests.Session()
        else:
            self.pool = pool
    
    def __getattr__(self, name):
        return API(
                '{0}/{1}'.format(self.endpoint, name),
                self.identity,
                self.private,
                self.public,
                self.pool
            )
    
    def __call__(self, *args, **kwargs):
        result = self.pool.post(
                self.endpoint + ( ('/' + '/'.join(args)) if args else '' ),
                data = kwargs,
                auth = SignedAuth(self.identity, self.private, self.public)
            )
        
        if not result.status_code == requests.codes.ok:
            return None
        
        return Bunch(result.json())
