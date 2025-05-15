import asyncio
import base64
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Coroutine, Dict, List, Optional

import httpx
import loguru
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from PIL import Image
from pydantic import BaseModel

from . import model

VERSION = "v0.19.1"  # 本库以此后端版本为基础编写，使用时请注意版本变动


def basic_auth(username: str, password: str) -> str:
    auth = username + ":" + password
    encoded = base64.b64encode(auth.encode("utf-8"))
    return "Basic " + encoded.decode("utf-8")


def replace_url(url: str) -> str:
    if url.startswith("http"):
        url = url.replace(":/", "").replace("?", "%3F")
    if not url.startswith("/"):
        url = "/" + url
    return url


class ApiException(Exception):
    def __init__(self, code: int, error: str):
        self.code = code
        self.error = error
        super().__init__(f"{self.error} ({self.code})")


class Result(BaseModel):
    code: int
    data: Optional[Any] = None
    error: Optional[str] = ""


class Session:
    """
    会话类

    基于 `httpx.AsyncClient`
    """

    def __init__(self, base_url: str, *args, **kwargs):
        """
        Args:
            base_url (str): 基础接口地址
        """
        self.session = httpx.AsyncClient(base_url=base_url, *args, **kwargs)

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
        """
        基础请求，仅检查状态码是否为 200 OK

        Args:
            method (str): 请求方法
            url (str): 请求地址
        """
        resp = await self.session.request(method, url, *args, **kwargs)
        if resp.status_code != 200:
            raise ApiException(resp.status_code, f"<Response [{resp.status_code}]>")
        return resp.content

    async def get(self, url: str, *args, **kwargs):
        return await self.request("GET", url, *args, **kwargs)

    async def post(self, url: str, *args, **kwargs):
        return await self.request("POST", url, *args, **kwargs)

    async def patch(self, url: str, body: List[model.PatchBody], *args, **kwargs):
        data = "[" + ",".join(patch.model_dump_json() for patch in body) + "]"
        return await self.request("PATCH", url, data=data, *args, **kwargs)

    async def delete(self, url: str, *args, **kwargs):
        return await self.request("DELETE", url, *args, **kwargs)


class OpenAPI(Session):
    """
    API 实现层
    """

    def __init__(self, base_url: str, token: str = ""):
        """
        Args:
            base_url (str): 接口基础地址
            token (str, optional): JWT 鉴权码
        """
        Session.__init__(self, base_url)
        self.set_token(token)

    async def request(self, method: str, url: str, *args, **kwargs) -> Optional[Any]:
        """
        检查业务码的请求

        Args:
            method (str): 请求方法
            url (str): 请求地址
        """
        r = Result.model_validate_json(await super().request(method, url, *args, **kwargs))
        if r.code != 0:
            raise ApiException(r.code, r.error)
        return r.data

    async def public(self, url: str) -> bytes:
        """
        可以获取服务器已保存的资源，也可以获取一个链接对应的资源

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

    async def version(self) -> model.Version:
        """
        获取后端的接口版本、环境版本、运行时间、主页文件名信息

        Returns:
            版本信息
        """
        return model.Version.model_validate(await self.get("/api/version"))

    async def valid(self) -> bool:
        """
        后端进行鉴权码校验并返回真假值

        Returns:
            鉴权码是否有效
        """
        return await self.get("/api/valid")

    async def ping(self) -> str:
        """
        后端记录当前时间作为用户最后一次在线时间

        Returns:
            pong
        """
        return await self.get("/api/ping")

    async def online(self) -> Dict[str, int]:
        """
        获取所有用户最后一次在线距离当前时间的差值，单位毫秒

        Returns:
            用户序号为键、时间为值的字典
        """
        return await self.get("/api/online")

    async def token(self, uid: str, password: str, refresh: bool = False) -> str:
        """
        获取或刷新鉴权码 Token

        Args:
            uid (str): 用户 ID
            password (str): 密码
            refresh (bool, optional): 是否刷新 Token

        Returns:
            鉴权码
        """
        return await self.get("/api/token", params={"refresh": refresh}, headers={"Authorization": basic_auth(uid, password)})

    async def get_blogs(
        self,
        condition: Optional[model.Condition] = None,
        filter: Optional[model.Filter] = None,
        mid: str = "",
        task_id: Optional[List[int]] = None,
    ) -> List[model.Blog]:
        """
        获取博文

        Args:
            condition (model.Condition): 查询条件
            filter (model.Filter): 筛选条件
            mid (str): 要获取博文的序号
            task_id (List[int]): 此参数非空时，会忽略 `Filter` 和 `mid` 参数，并从所有公开或本人的任务中匹配任务序号，再合并所有匹配成功的任务的筛选条件，最后用这些条件筛选出博文

        Returns:
            博文列表
        """
        query = {}
        if condition is not None:
            query.update(condition.model_dump())
        if filter is not None:
            query.update(filter.model_dump())
        if mid != "":
            query["mid"] = mid
        if task_id is not None:
            query["task_id"] = task_id
        r = await self.get("/api/blogs", params=query)
        blogs = []
        for blog in r:
            blogs.append(model.Blog.model_validate(blog))
        return blogs

    async def post_blogs(
        self,
        condition: Optional[model.Condition] = None,
        filters: Optional[List[model.Filter]] = None,
    ) -> List[model.Blog]:
        """
        获取筛选后博文

        Args:
            condition (model.Condition): 查询条件
            filters (List[model.Filter]): 筛选条件

        Returns:
            博文列表
        """
        data = {}
        if condition is not None:
            data.update(condition.model_dump())
        if filters is not None:
            f = []
            for filter in filters:
                f.append(filter.model_dump())
            data["filters"] = f
        r = await self.post("/api/blogs", json=data)
        blogs = []
        for blog in r:
            blogs.append(model.Blog.model_validate(blog))
        return blogs

    async def get_blog(self, blog_id: int) -> model.Blog:
        """
        获取单条博文

        Args:
            blog_id (int): 博文 ID

        Returns:
            单条博文
        """
        return model.Blog.model_validate(await self.get(f"/api/blog/{blog_id}"))

    async def get_tasks(self, key: str = "", limit: int = 30, offset: int = 0) -> List[model.Task]:
        """
        获取任务集

        Args:
            key (str): 关键词，用来在任务名和描述中搜索
            limit (int): 查询行数
            offset (int): 查询偏移

        Returns:
            任务列表
        """
        r = await self.get("/api/tasks", params={"key": key, "limit": limit, "offset": offset})
        tasks = []
        for task in r:
            tasks.append(model.Task.model_validate(task))
        return tasks

    async def post_user(self):
        """
        注册账户，具体请求方式由后端使用的注册函数决定
        """
        raise NotImplementedError

    async def get_user(self, uid: str) -> model.User:
        """
        获取指定用户信息，结果不包含任务 Tasks 信息

        Args:
            uid (str): 用户 ID

        Returns:
            用户
        """
        return model.User.model_validate(await self.get(f"/api/user/{uid}"))

    async def me(self) -> model.User:
        """
        获取自身用户信息，结果包含任务 Tasks 信息

        Returns:
            自身用户
        """
        return model.User.model_validate(await self.get("/api/user"))

    async def patch_user(self, uid: str, body: List[model.PatchBody]) -> str:
        """
        修改指定用户信息。每个用户均可修改自身部分信息，管理者可以修改权限低于自身的用户的部分信息，例如：昵称、封禁时间等。

        用户可选操作包括：

        | 操作路径  | 操作类型 | 操作含义       |
        | --------- | -------- | -------------- |
        | /nickname | replace  | 修改自己的昵称 |

        管理者可选操作包括：

        | 操作路径  | 操作类型 | 操作含义                                                     |
        | --------- | -------- | ------------------------------------------------------------ |
        | /nickname | replace  | 修改自己或权限低于自己的用户的昵称                           |
        | /name     | replace  | 修改自己或权限低于自己的用户的用户名                         |
        | /role     | replace  | 修改权限低于自己的用户的权限，数值大于 `0` 且小于自身权限等级 |
        | /ban      | replace  | 修改权限低于自己的用户的封禁时间，参数采用 `RFC3339` 时间格式 |
        |           | add      | 添加权限低于自己的用户的封禁时间，参数以毫秒为单位的数字字符串 |
        |           | remove   | 移除权限低于自己的用户的封禁时间                             |

        Args:
            uid (str): 用户 ID
            body (List[model.PatchBody]): 请求体

        Returns:
            success
        """
        return await self.patch(f"/api/user/{uid}", body)

    async def following(self, condition: Optional[model.Condition] = None) -> List[model.Blog]:
        """
        获取自己的任务能匹配的博文

        Args:
            condition (model.Condition): 查询条件

        Returns:
            博文列表
        """
        query = {}
        if condition is not None:
            query.update(condition.model_dump())
        r = await self.get("/api/following", params=query)
        blogs = []
        for blog in r:
            blogs.append(model.Blog.model_validate(blog))
        return blogs

    async def post_blog(self, blog: model.Blog) -> int:
        """
        提交博文

        Args:
            blog (model.Blog): 要提交的博文

        Returns:
            博文 ID
        """
        return await self.post("/api/blog", data=blog.model_dump_json())

    async def post_task(self, task: model.Task) -> int:
        """
        提交任务

        Args:
            task (model.Task): 要提交的任务

        Returns:
            任务 ID
        """
        return await self.post("/api/task", data=task.model_dump_json())

    async def get_task(self, task_id: int, limit: int = 30, offset: int = 0) -> model.Task:
        """
        获取公开或自己的任务信息

        Args:
            task_id (int): 任务 ID
            limit (int): 查询行数
            offset (int): 查询偏移

        Returns:
            任务
        """
        return model.Task.model_validate(await self.get(f"/api/task/{task_id}", params={"limit": limit, "offset": offset}))

    async def patch_task(self, task_id: int, body: List[model.PatchBody]) -> str:
        """
        修改自己的任务

        可选操作包括：

        | 操作路径 | 操作类型 | 操作含义                                                     |
        | -------- | -------- | ------------------------------------------------------------ |
        | /public  | add      | 将任务公开，公开后不可取消公开                               |
        | /enable  | replace  | 修改任务是否启用，参数为真假值                               |
        | /name    | replace  | 修改任务名称                                                 |
        | /icon    | replace  | 修改任务图标链接                                             |
        | /method  | replace  | 修改任务请求方法                                             |
        | /url     | replace  | 修改任务请求地址                                             |
        | /body    | replace  | 修改任务请求体                                               |
        | /header  | replace  | 修改任务请求头，参数为 `JSON` 格式的 `map[string]string`     |
        | /readme  | replace  | 修改任务描述                                                 |
        | /filters | replace  | 修改任务筛选条件，参数为 `JSON` 格式的 [Filter](#筛选条件) 列表 |

        Args:
            task_id (int): 任务序号 ID
            body (List[model.PatchBody]): 请求体

        Returns:
            success
        """
        return await self.patch(f"/api/task/{task_id}", body)

    async def delete_task(self, task_id: str) -> str:
        """
        删除指定任务

        Args:
            task_id (str): 任务 ID

        Returns:
            success
        """
        return await self.delete(f"/api/task/{task_id}")

    async def test(
        self,
        blog: Optional[model.Blog] = None,
        task: Optional[model.Task] = None,
        blog_id: int = 0,
        task_id: Optional[List[int]] = None,
    ) -> List[model.RequestLog]:
        """
        测试已保存或请求体内上传的任务

        Args:
            blog (model.Blog): 测试用博文
            task (model.Task): 待测试任务
            blog_id (int): 测试用博文序号，优先于上传的博文使用
            task_id (List[int]): 待测试博文序号，优先于上传的任务使用

        Returns:
            请求记录
        """
        data = model.Test(blog=blog, task=task, blog_id=blog_id, task_id=task_id)
        r = await self.post("/api/test", data=data.model_dump_json())
        logs = []
        for log in r:
            logs.append(model.RequestLog.model_validate(log))
        return logs


class Client(OpenAPI):
    """
    客户端
    """

    def __init__(self, base_url: str, uid: str = "", password: str = "", token: str = "", log: bool = True, ping: float = -1):
        """
        Args:
            base_url (str): 接口基础地址
            uid (str): 用户序号
            password (str): 密码
            token (str): JWT 鉴权码
            log (bool): 是否将日志打印在文件
            ping (float): 与后端心跳间隔秒数，非正数则不开启
        """
        OpenAPI.__init__(self, base_url, token)
        self.uid = uid
        self.password = password
        self.log = loguru.logger
        if log:
            self.log.add(
                sink="{time:YYYY-MM-DD}.log",
                level="ERROR",
                rotation="00:00",
                encoding="utf-8",
                enqueue=True,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | " "<level>{level}</level> | " "<cyan>{name}.{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            )
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        if ping > 0:
            self.add_job(self.ping, interval=ping, delay=ping)

    def __call__(self, fn: Coroutine):
        async def main():
            try:
                # 提供了 Token 则检验
                if self.get_token() != "":
                    if not await self.valid():
                        self.set_token("")

                # 未提供或者检验失败则在已有账密的情况下获取 Token
                if self.get_token() == "" and self.uid != "" and self.password != "":
                    self.set_token(await self.token(self.uid, self.password))

                # 开始任务轮询
                self.scheduler.start()
                await fn(self)
            except:
                if self.scheduler.running:
                    self.scheduler.shutdown(False)
                loop.stop()
                raise

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(self.catch(main, 2)())
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        except:
            raise

    def stop(self):
        asyncio.get_event_loop().stop()

    def catch(self, fn: Coroutine, depth: int = 1):
        """
        捕获错误

        Args:
            fn (Coroutine): 要运行的异步函数
            depth (int): 打印错误时翻越错误栈层数
        """

        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                if self.log is not None:
                    msg = type(e).__name__
                    if str(e) != "":
                        msg += f": {str(e)}"
                    traceback = e.__traceback__
                    for _ in range(depth):
                        traceback = traceback.tb_next
                    name = Path(traceback.tb_frame.f_code.co_filename).stem
                    line = traceback.tb_frame.f_lineno
                    function = fn.__name__

                    def modify_record(record):
                        record["name"] = name
                        record["line"] = line
                        record["function"] = function

                    try:
                        self.log.patch(modify_record).error(msg)
                    except:
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        print(f"{now}.000 | ERROR    | {name}:{function}:{line} - {msg}")

        return wrapper

    def add_job(self, fn: Coroutine, interval: float, delay: float = 0, *args, **kwargs):
        """
        新增任务

        Args:
            fn (Coroutine): 函数
            interval (float): 执行间隔秒数
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
            interval (float): 执行间隔秒数
            delay (float, optional): 第一次执行前延时
        """
        return lambda fn: self.add_job(fn, interval, delay, *args, **kwargs)
