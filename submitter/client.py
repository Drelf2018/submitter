import asyncio
import base64
import sys
from datetime import datetime, timedelta
from typing import Any, Coroutine, Dict, List, Optional

import httpx
import loguru
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel

from . import code, model


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
                error=f"<Response [{resp.status_code}]>: {code.get(resp.status_code)}",
            )
            try:
                e.data = resp.json()
            except:
                e.data = resp.content
            raise e

        return resp.content

    async def check_code(self, method: str, url: str, *args, **kwargs) -> Any:
        r = Result.model_validate_json(await self.request(method, url, *args, **kwargs))
        if r.code != 0:
            raise ApiException(r.code, r.error, r.data)
        return r.data

    async def get(self, url: str, *args, **kwargs):
        return await self.check_code("GET", url, *args, **kwargs)

    async def post(self, url: str, *args, **kwargs):
        return await self.check_code("POST", url, *args, **kwargs)

    async def patch(self, url: str, body: List[model.PatchBody], *args, **kwargs):
        data = "[" + ",".join(patch.model_dump_json() for patch in body) + "]"
        return await self.check_code("PATCH", url, data=data, *args, **kwargs)

    async def delete(self, url: str, *args, **kwargs):
        return await self.check_code("DELETE", url, *args, **kwargs)


class OpenAPI(Session):
    """
    Api 实现层
    """

    def __init__(self, base_url: str, token: str = ""):
        """
        Args:
            base_url (str): 接口基础地址

            token (str): JWT 鉴权码
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
        """
        if url.startswith("http"):
            url = url.replace(":/", "")
        if not url.startswith("/"):
            url = "/" + url
        return await self.request("GET", "/public" + url)

    async def register(self):
        """
        注册

        *不同服务端自行实现*
        """
        raise NotImplemented

    async def token(self, uid: str, password: str, refresh: bool = False) -> str:
        """
        获取鉴权码 Token
        """
        return await self.get("/token", params={"refresh": refresh}, headers={"Authorization": basic_auth(uid, password)})

    async def uuid(self, uid: str):
        """
        查询用户信息
        """
        return model.User.model_validate(await self.get(f"/u/{uid}"))

    async def filter(self, filter: model.BlogFilter) -> List[model.Blog]:
        """
        筛选博文
        """
        r = await self.post("/filter", data=filter.model_dump_json())
        blogs = []
        for blog in r:
            blogs.append(model.Blog.model_validate(blog))
        return blogs

    async def blogs(self, query: model.BlogQuery) -> List[model.Blog]:
        """
        查询博文
        """
        r = await self.get("/blogs", params=query)
        blogs = []
        for blog in r:
            blogs.append(model.Blog.model_validate(blog))
        return blogs

    async def get_blog(self, blog_id: int) -> model.Blog:
        """
        查询单条博文
        """
        return model.Blog.model_validate(await self.get(f"/blog/{blog_id}"))

    async def post_blog(self, blog: model.Blog) -> int:
        """
        提交博文
        """
        return await self.post("/user/blog", data=blog.model_dump_json())

    async def post_task(self, task: model.Task) -> int:
        """
        新增任务
        """
        return await self.post("/user/task", data=task.model_dump_json())

    async def get_task(self, task_id: int) -> model.Task:
        """
        查询任务
        """
        return model.Task.model_validate(await self.get(f"/user/task/{task_id}"))

    async def patch_task(self, task_id: int, body: List[model.PatchBody]) -> str:
        """
        修改任务
        """
        return await self.patch(f"/user/task/{task_id}", body)

    async def delete_task(self, task_id: str) -> str:
        """
        移除任务
        """
        return await self.delete(f"/user/task/{task_id}")

    async def me(self) -> model.User:
        """
        获取自身信息
        """
        return model.User.model_validate(await self.get("/user"))

    async def patch_user(self, uid: str, body: List[model.PatchBody]) -> str:
        """
        修改用户信息
        """
        return await self.patch(f"/user/{uid}", body)

    async def test(self, blog: model.Blog, task: model.Task) -> model.RequestLog:
        """
        测试单个任务
        """
        r = await self.post("/user/test", data=model.Test(blog=blog, task=task).model_dump_json())
        return model.RequestLog.model_validate(r)

    async def tests(self, blog: model.Blog, tasks: List[int]) -> List[model.RequestLog]:
        """
        测试任务
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
        """
        next = datetime.now() + timedelta(seconds=delay)
        self.scheduler.add_job(self.catch(fn), "interval", next_run_time=next, seconds=interval, args=args, kwargs=kwargs)
        return fn

    def job(self, interval: float, delay: float = 0, *args, **kwargs):
        """
        新增任务装饰器
        """
        return lambda fn: self.add_job(fn, interval, delay, *args, **kwargs)
