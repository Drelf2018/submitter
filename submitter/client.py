import asyncio
import base64
import sys
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Coroutine, Dict, List, Optional

import httpx
import loguru
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from PIL import Image
from pydantic import BaseModel

from . import model

# Copied from requests.status_codes because they are not exported
codes = {
    # Informational.
    100: "continue",
    101: "switching_protocols",
    102: "processing",
    103: "checkpoint",
    122: "uri_too_long",
    200: "ok",
    201: "created",
    202: "accepted",
    203: "non_authoritative_info",
    204: "no_content",
    205: "reset_content",
    206: "partial_content",
    207: "multi_status",
    208: "already_reported",
    226: "im_used",
    # Redirection.
    300: "multiple_choices",
    301: "moved_permanently",
    302: "found",
    303: "see_other",
    304: "not_modified",
    305: "use_proxy",
    306: "switch_proxy",
    307: "temporary_redirect",
    308: "permanent_redirect",  # "resume" and "resume_incomplete" to be removed in 3.0
    # Client Error.
    400: "bad_request",
    401: "unauthorized",
    402: "payment_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    407: "proxy_authentication_required",
    408: "request_timeout",
    409: "conflict",
    410: "gone",
    411: "length_required",
    412: "precondition_failed",
    413: "request_entity_too_large",
    414: "request_uri_too_large",
    415: "unsupported_media_type",
    416: "requested_range_not_satisfiable",
    417: "expectation_failed",
    418: "im_a_teapot",
    421: "misdirected_request",
    422: "unprocessable_entity",
    423: "locked",
    424: "failed_dependency",
    425: "unordered_collection",
    426: "upgrade_required",
    428: "precondition_required",
    429: "too_many_requests",
    431: "header_fields_too_large",
    444: "no_response",
    449: "retry_with",
    450: "blocked_by_windows_parental_controls",
    451: "unavailable_for_legal_reasons",
    499: "client_closed_request",
    # Server Error.
    500: "internal_server_error",
    501: "not_implemented",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
    505: "http_version_not_supported",
    506: "variant_also_negotiates",
    507: "insufficient_storage",
    509: "bandwidth_limit_exceeded",
    510: "not_extended",
    511: "network_authentication_required",
}


def basic_auth(username: str, password: str) -> str:
    auth = username + ":" + password
    encoded = base64.b64encode(auth.encode("utf-8"))
    return "Basic " + encoded.decode("utf-8")


class ApiException(Exception):
    def __init__(self, code: int, error: str, data: Any = None):
        self.code = code
        self.error = error
        self.data = data
        super().__init__(f"ApiException: {self.error} ({self.code})")


class Result(BaseModel):
    code: int
    data: Optional[Any] = None
    error: Optional[str] = ""


class Session:
    """
    会话类

    基于 `httpx.AsyncClient`
    """

    def __init__(self, base_url: str):
        """
        Args:
            base_url (str): 基础接口地址
        """
        self.session = httpx.AsyncClient(base_url=base_url)

    def set_token(self, token: str):
        """
        设置本地鉴权码
        """
        self.session.headers["Authorization"] = token

    def get_token(self) -> str:
        """
        获取本地鉴权码
        """
        return self.session.headers["Authorization"]

    async def request(self, method: str, url: str, *args, **kwargs) -> bytes:
        resp = await self.session.request(method, url, *args, **kwargs)
        if resp.status_code != 200:
            e = ApiException(
                code=resp.status_code,
                error=f"<Response [{resp.status_code}]>: {codes.get(resp.status_code, 'unknown status code')}",
            )
            try:
                e.data = resp.json()
            except:
                e.data = resp.content
            raise e
        return resp.content

    async def check_code(self, data: bytes) -> Any:
        r = Result.model_validate_json(data)
        if r.code != 0:
            raise ApiException(r.code, r.error, r.data)
        return r.data

    async def get(self, url: str, *args, **kwargs):
        r = await self.request("GET", url, *args, **kwargs)
        return await self.check_code(r)

    async def post(self, url: str, *args, **kwargs):
        r = await self.request("POST", url, *args, **kwargs)
        return await self.check_code(r)

    async def patch(self, url: str, body: List[model.PatchBody], *args, **kwargs):
        data = "[" + ",".join(patch.model_dump_json() for patch in body) + "]"
        r = await self.request("PATCH", url, data=data, *args, **kwargs)
        return await self.check_code(r)

    async def delete(self, url: str, *args, **kwargs):
        r = await self.request("DELETE", url, *args, **kwargs)
        return await self.check_code(r)


def replace_url(url: str) -> str:
    if url.startswith("http"):
        url = url.replace(":/", "")
    if not url.startswith("/"):
        url = "/" + url
    return url


class OpenAPI(Session):
    """
    Api 实现层
    """

    def __init__(self, base_url: str, token: str = ""):
        """
        Args:
            base_url (str): 接口基础地址
            token (str, optional): JWT 鉴权码
        """
        Session.__init__(self, base_url)
        self.set_token(token)

    async def version(self) -> Dict[str, str]:
        """
        获取服务端版本
        """
        return await self.get("/version")

    async def valid(self) -> bool:
        """
        鉴权码检验
        """
        return await self.get("/valid")

    async def ping(self) -> str:
        """
        更新自身在线状态
        """
        return await self.get("/ping")

    async def online(self) -> Dict[str, int]:
        """
        获取当前在线状态
        """
        return await self.get("/online")

    async def public(self, url: str) -> bytes:
        """
        解析资源网址

        Args:
            url (str): 网址

        Returns:
            数据
        """
        return await self.request("GET", "/public" + replace_url(url))

    async def image(self, url: str) -> Optional[Image.Image]:
        """
        解析图片网址，资源非图像时返回 None

        Args:
            url (str): 图片网址

        Returns:
            可能为 `None` 的 `Image.Image` 对象
        """
        resp = await self.session.get("/public" + replace_url(url))
        if resp.status_code != 200:
            return None
        if not resp.headers["Content-Type"].startswith("image"):
            return None
        return Image.open(BytesIO(resp.content))

    async def forward(self, method: str, url: str, *args, **kwargs) -> bytes:
        """
        请求转发

        Args:
            method (str): 请求方式
            url (str): 请求网址

        Returns:
            原请求数据
        """
        return await self.request(method, "/forward" + replace_url(url), *args, **kwargs)

    async def register(self):
        """
        注册

        *不同服务端自行实现*
        """
        raise NotImplementedError

    async def token(self, uid: str, password: str, refresh: bool = False) -> str:
        """
        获取鉴权码 Token

        Args:
            uid (str): 用户 ID
            password (str): 密码
            refresh (bool, optional): 是否刷新 Token

        Returns:
            鉴权码
        """
        return await self.get("/token", params={"refresh": refresh}, headers={"Authorization": basic_auth(uid, password)})

    async def uuid(self, uid: str):
        """
        查询用户信息

        Args:
            uid (str): 用户 ID

        Returns:
            用户
        """
        return model.User.model_validate(await self.get(f"/u/{uid}"))

    async def filter(self, filter: model.BlogFilter) -> List[model.Blog]:
        """
        筛选博文

        Args:
            filter (model.BlogFilter): 筛选器

        Returns:
            博文列表
        """
        r = await self.post("/filter", data=filter.model_dump_json())
        blogs = []
        for blog in r:
            blogs.append(model.Blog.model_validate(blog))
        return blogs

    async def blogs(self, query: model.BlogQuery) -> List[model.Blog]:
        """
        查询博文

        Args:
            query (model.BlogQuery): 查询条件

        Returns:
            博文列表
        """
        r = await self.get("/blogs", params=query)
        blogs = []
        for blog in r:
            blogs.append(model.Blog.model_validate(blog))
        return blogs

    async def get_blog(self, blog_id: int) -> model.Blog:
        """
        查询单条博文

        Args:
            blog_id (int): 博文 ID

        Returns:
            单条博文
        """
        return model.Blog.model_validate(await self.get(f"/blog/{blog_id}"))

    async def post_blog(self, blog: model.Blog) -> int:
        """
        提交博文

        Args:
            blog (model.Blog): 要提交的博文

        Returns:
            博文 ID
        """
        return await self.post("/user/blog", data=blog.model_dump_json())

    async def post_task(self, task: model.Task) -> int:
        """
        新增任务

        Args:
            task (model.Task): 要添加的任务

        Returns:
            任务 ID
        """
        return await self.post("/user/task", data=task.model_dump_json())

    async def get_task(self, task_id: int) -> model.Task:
        """
        查询任务

        Args:
            task_id (int): 任务 ID

        Returns:
            单条任务
        """
        return model.Task.model_validate(await self.get(f"/user/task/{task_id}"))

    async def patch_task(self, task_id: int, body: List[model.PatchBody]) -> str:
        """
        修改任务

        Args:
            task_id (int): 任务序号 ID
            body (List[model.PatchBody]): 请求体

        Returns:
            是否修改成功
        """
        return await self.patch(f"/user/task/{task_id}", body)

    async def delete_task(self, task_id: str) -> str:
        """
        移除任务

        Args:
            task_id (str): 任务 ID

        Returns:
            是否移除成功
        """
        return await self.delete(f"/user/task/{task_id}")

    async def me(self) -> model.User:
        """
        获取自身信息

        Returns:
            自身用户
        """
        return model.User.model_validate(await self.get("/user"))

    async def patch_user(self, uid: str, body: List[model.PatchBody]) -> str:
        """
        修改用户信息

        Args:
            uid (str): 用户 ID
            body (List[model.PatchBody]): 请求体

        Returns:
            是否修改成功
        """
        return await self.patch(f"/user/{uid}", body)

    async def test(self, blog: model.Blog, task: model.Task) -> model.RequestLog:
        """
        测试单个任务

        Args:
            blog (model.Blog): 要应用的博文
            task (model.Task): 要测试的任务

        Returns:
            请求记录
        """
        r = await self.post("/user/test", data=model.Test(blog=blog, task=task).model_dump_json())
        return model.RequestLog.model_validate(r)

    async def tests(self, blog: model.Blog, tasks: List[int]) -> List[model.RequestLog]:
        """
        测试多个任务（必须是服务端已存在的）

        Args:
            blog (model.Blog): 要应用的博文
            tasks (List[int]): 任务集序号

        Returns:
            请求记录列表
        """
        r = await self.post("/user/tests", data=model.Tests(blog=blog, tasks=tasks).model_dump_json())
        logs = []
        for log in r:
            logs.append(model.RequestLog.model_validate(log))
        return logs


def log_filter(record: dict):
    extra = record["extra"]
    return extra.get("log_name") == "client" and "name" in extra and "function" in extra and "line" in extra


class Client(OpenAPI):
    def __init__(self, base_url: str, uid: str = "", password: str = "", token: str = "", ping: float = -1):
        OpenAPI.__init__(self, base_url, token)
        self.uid = uid
        self.password = password
        self.log = loguru.logger.bind(log_name="client")
        self.log.add(
            sys.stderr,
            colorize=True,
            level="ERROR",
            enqueue=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | " "<level>{level: <8}</level> | " "<cyan>{extra[name]}</cyan>:<cyan>{extra[function]}</cyan>:<cyan>{extra[line]}</cyan> - <level>{message}</level>",
            filter=log_filter,
        )
        self.log.add(
            sink="{time:YYYY-MM-DD}.log",
            level="ERROR",
            rotation="00:00",
            encoding="utf-8",
            enqueue=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | " "<level>{level}</level> | " "<cyan>{extra[name]}.{extra[function]}</cyan>:<cyan>{extra[line]}</cyan> | <level>{message}</level>",
            filter=log_filter,
        )
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        if ping > 0:
            self.add_job(self.ping, interval=ping, delay=ping)

    def __call__(self, fn: Coroutine):
        async def main():
            if self.get_token() != "":
                if not await self.valid():
                    try:
                        self.set_token(await self.token(self.uid, self.password))
                    except Exception as e:
                        if self.log is not None:
                            self.log.error(str(e), name="client", function="login", line=e.__traceback__.tb_lineno)
                        loop.stop()

            self.scheduler.start()
            if not await self.catch(fn)(self):
                loop.stop()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(main())
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        except:
            raise
        self.scheduler.shutdown(False)
        return fn

    def catch(self, fn: Coroutine):
        async def wrapper(*args, **kwargs) -> bool:
            try:
                await fn(*args, **kwargs)
                return True
            except Exception as e:
                if self.log is not None:
                    file = e.__traceback__.tb_next.tb_frame.f_code.co_filename.split(".")[-2].split("\\")[-1]
                    try:
                        self.log.error(str(e), name=file, function=fn.__name__, line=e.__traceback__.tb_next.tb_frame.f_lineno)
                    except:
                        print(e)
                return False

        return wrapper

    def add_job(self, fn: Coroutine, interval: float, delay: float = 0, *args, **kwargs):
        """
        新增任务

        Args:
            fn (Coroutine): 函数
            interval (float): 执行间隔
            delay (float, optional): 第一次执行前延时

        Returns:
            原函数
        """
        next = datetime.now() + timedelta(seconds=delay)
        self.scheduler.add_job(self.catch(fn), "interval", next_run_time=next, seconds=interval, args=args, kwargs=kwargs)
        return fn

    def job(self, interval: float, delay: float = 0, *args, **kwargs):
        """
        新增任务装饰器

        Args:
            interval (float): 执行间隔
            delay (float, optional): 第一次执行前延时
        """
        return lambda fn: self.add_job(fn, interval, delay, *args, **kwargs)
