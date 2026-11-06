import os
import asyncio
import logging
from contextlib import asynccontextmanager
from collections import OrderedDict
from io import BytesIO
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from python_multipart.exceptions import MultipartParseError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect

from .contracts import APIError, Celebrity, MatchResponse
from .inference import load_matcher

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_BODY_BYTES = MAX_FILE_BYTES + 64 * 1024
MAX_PIXELS = 20_000_000
FORMATS = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str
    matchingReady: bool
    reason: str


class CelebritiesResponse(BaseModel):
    celebrities: list[Celebrity]
    total: int


def error_response(status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}})


def validate_image(data: bytes, content_type: str | None):
    if not data:
        raise APIError(422, 'EMPTY_IMAGE', 'Choose a non-empty image.')
    if len(data) > MAX_FILE_BYTES:
        raise APIError(413, 'IMAGE_TOO_LARGE', 'Choose an image no larger than 10 MB.')
    if content_type not in FORMATS.values():
        raise APIError(415, 'UNSUPPORTED_IMAGE', 'Use JPEG, PNG, or WebP.')
    try:
        with Image.open(BytesIO(data), formats=list(FORMATS)) as image:
            if FORMATS[image.format] != content_type:
                raise APIError(415, 'IMAGE_TYPE_MISMATCH', 'Image content does not match its declared type.')
            if image.width * image.height > MAX_PIXELS:
                raise APIError(413, 'IMAGE_DIMENSIONS_TOO_LARGE', 'Choose an image with at most 20 megapixels.')
            if getattr(image, 'n_frames', 1) != 1:
                raise APIError(422, 'ANIMATED_IMAGE', 'Choose a still image.')
            image.verify()
        with Image.open(BytesIO(data), formats=list(FORMATS)) as image:
            image.load()
    except Image.DecompressionBombError:
        raise APIError(413, 'IMAGE_DIMENSIONS_TOO_LARGE', 'Choose a smaller image.') from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise APIError(422, 'INVALID_IMAGE', 'This file could not be decoded as an image.') from None


def create_app(matcher=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.matcher = matcher
        if matcher is None:
            try:
                app.state.matcher = await run_in_threadpool(load_matcher)
            except Exception:
                logging.getLogger(__name__).error('Matching setup failed. Check local models and rebuild the catalog.')
        if os.getenv('CELEBRY_REQUIRE_READY', 'false').lower() == 'true' and app.state.matcher is None:
            raise RuntimeError('Inference must be ready before this deployment starts')
        yield
        app.state.matcher = None

    app = FastAPI(title='Celebry API', version='0.5.0', lifespan=lifespan)
    app.state.matcher = matcher
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv('CELEBRY_CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(','),
        allow_methods=['GET', 'POST'],
        allow_headers=['Content-Type'],
    )
    # shortcut: per-process rate limits, use a shared gateway before scaling to multiple workers.
    buckets: OrderedDict[str, list[float]] = OrderedDict()
    limit = int(os.getenv('CELEBRY_RATE_LIMIT', '10'))
    upload_timeout = float(os.getenv('CELEBRY_UPLOAD_TIMEOUT_SECONDS', '30'))
    concurrency = int(os.getenv('CELEBRY_MAX_PROCESSING', '2'))
    if limit < 1 or upload_timeout <= 0 or concurrency < 1:
        raise ValueError('Rate limit, upload timeout, and concurrency must be positive')
    processing_slots = asyncio.Semaphore(concurrency)

    @app.middleware('http')
    async def prevent_caching(request, call_next):
        started = monotonic()
        response = await call_next(request)
        response.headers.setdefault('Cache-Control', 'no-store')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        path = request.url.path if request.url.path in {'/api/match', '/api/health', '/api/ready', '/api/celebrities'} else 'other'
        logging.getLogger('celebry.requests').info('method=%s path=%s status=%d duration_ms=%.1f', request.method, path, response.status_code, (monotonic() - started) * 1000)
        return response

    @app.exception_handler(APIError)
    async def api_error(_request, exc):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        return error_response(exc.status_code, 'HTTP_ERROR', 'Request could not be processed.')

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _exc):
        return error_response(422, 'VALIDATION_ERROR', 'Check the request fields.')

    @app.exception_handler(Exception)
    async def unexpected_error(_request, _exc):
        return error_response(500, 'INTERNAL_ERROR', 'Something went wrong. Please try again.')

    @app.get('/api/health', response_model=HealthResponse)
    async def health():
        ready = app.state.matcher is not None
        return {'status': 'ok', 'matchingReady': ready, 'reason': 'Ready.' if ready else 'Matching is unavailable. Configure compatible local models and celebrity catalog.'}

    @app.get('/api/ready', responses={503: {'model': ErrorResponse}})
    async def readiness():
        if app.state.matcher is None:
            raise APIError(503, 'MATCHING_NOT_READY', 'Inference is not ready.')
        return {'status': 'ready', 'celebrities': len(app.state.matcher.celebrities)}

    @app.get('/media/celebrities/{identifier}.jpg', response_class=Response, responses={404: {'model': ErrorResponse}})
    async def celebrity_photo(identifier: str):
        engine = app.state.matcher
        photo = engine.photos.get(identifier) if engine else None
        if photo is None:
            raise APIError(404, 'PHOTO_NOT_FOUND', 'Celebrity photo not found.')
        return Response(photo, media_type='image/jpeg', headers={'Cache-Control': 'public, max-age=86400'})

    @app.get('/api/celebrities', response_model=CelebritiesResponse)
    async def celebrities():
        people = app.state.matcher.celebrities if app.state.matcher else []
        return {'celebrities': people, 'total': len(people)}

    @app.post('/api/match', response_model=MatchResponse, responses={code: {'model': ErrorResponse} for code in (400, 413, 415, 422, 429, 503)},
              openapi_extra={'requestBody': {'required': True, 'content': {'multipart/form-data': {'schema': {
                  'type': 'object', 'required': ['photo', 'consent'], 'properties': {
                      'photo': {'type': 'string', 'format': 'binary'},
                      'consent': {'type': 'string', 'enum': ['true']}}}}}}})
    async def match(request: Request):
        if processing_slots.locked():
            raise APIError(503, 'MATCHING_BUSY', 'Analysis is busy. Please try again shortly.')
        await processing_slots.acquire()
        try:
            return await process_match(request)
        finally:
            processing_slots.release()

    async def process_match(request: Request):
        now = monotonic()
        key = request.client.host if request.client else 'unknown'
        hits = [t for t in buckets.pop(key, []) if now - t < 60]
        if len(hits) >= limit:
            buckets[key] = hits
            response = error_response(429, 'RATE_LIMITED', 'Too many requests. Try again in a minute.')
            response.headers['Retry-After'] = '60'
            return response
        buckets[key] = hits + [now]
        if len(buckets) > 1024:
            buckets.popitem(last=False)
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'multipart/form-data':
            raise APIError(415, 'UNSUPPORTED_REQUEST', 'Send a multipart form with photo and consent fields.')
        declared_size = request.headers.get('content-length')
        if declared_size is not None:
            try:
                size = int(declared_size)
            except ValueError:
                raise APIError(400, 'INVALID_REQUEST_SIZE', 'Invalid Content-Length.') from None
            if size < 0:
                raise APIError(400, 'INVALID_REQUEST_SIZE', 'Invalid Content-Length.')
            if size > MAX_BODY_BYTES:
                raise APIError(413, 'REQUEST_TOO_LARGE', 'Upload exceeds the 10 MB image limit.')
        body = bytearray()
        try:
            async with asyncio.timeout(upload_timeout):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        raise APIError(413, 'REQUEST_TOO_LARGE', 'Upload exceeds the 10 MB image limit.')
                    body.extend(chunk)
        except TimeoutError:
            raise APIError(408, 'UPLOAD_TIMEOUT', 'Upload took too long. Please try again.') from None
        except ClientDisconnect:
            raise APIError(400, 'UPLOAD_DISCONNECTED', 'Upload connection was interrupted.') from None

        async def stream():
            yield bytes(body)

        parser = MultiPartParser(request.headers, stream(), max_files=1, max_fields=1, max_part_size=1024)
        try:
            try:
                form = await parser.parse()
            except (MultiPartException, MultipartParseError):
                raise APIError(400, 'INVALID_MULTIPART', 'Send one photo and one consent field.') from None
            try:
                if set(form.keys()) != {'photo', 'consent'} or len(form.multi_items()) != 2:
                    raise APIError(422, 'INVALID_FIELDS', 'Provide exactly one photo and consent field.')
                if form.get('consent') != 'true':
                    raise APIError(422, 'CONSENT_REQUIRED', 'Explicit consent is required before processing a photo.')
                photo = form.get('photo')
                if not isinstance(photo, UploadFile):
                    raise APIError(422, 'PHOTO_REQUIRED', 'Provide a photo file.')
                data = await photo.read(MAX_FILE_BYTES + 1)
                await run_in_threadpool(validate_image, data, photo.content_type)
            finally:
                await form.close()
        finally:
            # Truncated parts may own spools absent from FormData; Starlette is pinned for this cleanup contract.
            for spool in parser._files_to_close_on_error:
                spool.close()
        if app.state.matcher is None:
            raise APIError(503, 'MATCHING_NOT_READY', 'Matching requires compatible local models and a licensed celebrity catalog. No analysis was performed.')
        return await run_in_threadpool(app.state.matcher.match, data)

    return app


app = create_app()
