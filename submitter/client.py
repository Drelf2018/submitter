import asyncio
import datetime
from typing import Coroutine, List, Optional, Tuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bilibili_api import Credential, comment, live
from loguru import logger

from .network import Api, ApiException


def delta(seconds: float):
    return datetime.datetime.now() + datetime.timedelta(seconds=seconds)


def run_forever(coro: Coroutine, *args, **kwargs):
    loop = asyncio.get_event_loop()
    loop.create_task(coro(*args, **kwargs))
    loop.run_forever()


class Client(Api, Credential):
    """
    客户端层
    
    对 Api 进一步封装
    """
    def __init__(
        self,
        url: str,
        auth: str | None = None,
        sessdata: str | None = None,
        bili_jct: str | None = None,
        dedeuserid: str | None = None,
    ):
        """
        `auth` 和 `dedeuserid` 可不填 若不填则自动获取 自动获取需要 `sessdata` 和 `bili_jct`

        如果 同时 填入 `auth` 和 `dedeuserid` 则不需要 `sessdata` 和 `bili_jct`

        Args:
            url: 基础接口地址
        
            auth: 鉴权码

            sessdata: 浏览器 Cookies 中的 SESSDATA 字段值. Defaults to None.

            bili_jct: 浏览器 Cookies 中的 bili_jct 字段值. Defaults to None.

            dedeuserid: 浏览器 Cookies 中的 DedeUserID 字段值. Defaults to None.
        """
        if auth is None:
            auth = ""
        Api.__init__(self, url, auth)
        Credential.__init__(self, sessdata=sessdata, bili_jct=bili_jct, dedeuserid=dedeuserid)

    async def get_self_uid(self) -> Tuple[str, Optional[Exception]]:
        """
        获取自身 uid
        """
        try:
            info = await live.get_self_info(self)
            return str(info["uid"]), None
        except Exception as e:
            return "", e

    async def get_self_auth(self) -> Tuple[str, Optional[Exception | ApiException]]:
        """
        获取自身鉴权码
        """
        data, err = await self.token(self.dedeuserid)
        if err is not None:
            return "", err
        try:
            await comment.send_comment(data["token"], data["oid"], comment.CommentResourceType.DYNAMIC, credential=self)
        except Exception as e:
            return "", e
        await asyncio.sleep(2)  # wait for bilibili update comment
        return await self.register(data["auth"])

    async def login(self) -> Optional[Exception | ApiException]:
        """
        登录
        """
        user, _ = await self.me()
        if self.dedeuserid is None:
            self.dedeuserid, err = await self.get_self_uid()
            if err is not None:
                return err
        if user.uid != self.dedeuserid:
            auth, err = await self.get_self_auth()
            if err is not None:
                return err
            self.set_auth(auth)
            user, _ = await self.me()
            if user.uid != self.dedeuserid:
                return ApiException("/login", 400, "Login failed.")
        return None


class Submitter(Client):
    """
    提交器

    use

    ```python
    async def main():
        async with Submitter(url, auth) as sub:
            @sub.job(0, 1)
            async def _():
                pass
    
    run_forever(main)
    ```

    or

    ```
    @Submitter(url, auth)
    async def _(sub: Submitter):
        @sub.job(0, 1)
        async def _():
            pass
    ```
    """
    async def __aenter__(self):
        self.__vaild = True
        self.__once: List[Coroutine] = []
        self.__scheduler = AsyncIOScheduler(timezone="Asia/Shanghai", event_loop=asyncio.get_running_loop())
        # 判断参数是否齐全
        if not all([self.auth, self.dedeuserid]) and not all([self.sessdata, self.bili_jct]):
            return await self.__aexit__(Exception, "请提供完整参数", None)
        # 模拟登录
        e = await self.login()
        if e is not None:
            return await self.__aexit__(e.__class__, str(e), None)
        return self

    async def __aexit__(self, typ_, value, trace):
        if not self.__vaild:
            return
        if typ_ is None:
            await self.__run__()
            return
        self.__vaild = False
        logger.error(f"{typ_.__name__}: {value}")
        asyncio.get_event_loop().stop()

    async def __run__(self):
        logger.info(f"auth: {self.auth}")
        logger.info(f"version: {await self.version()}")
        if len(self.__once) != 0:
            await asyncio.wait(self.__once)
        if len(self.__scheduler.get_jobs()) == 0:
            asyncio.get_event_loop().stop()
        else:
            self.__scheduler.start()

    def __call__(self, fn: Coroutine):
        async def main():
            if await self.__aenter__() is None:
                return
            try:
                await fn(self)
                await self.__run__()
            except Exception as e:
                await self.__aexit__(e.__class__, str(e), None)
        run_forever(main)

    def add_once(self, fn: Coroutine, *args, **kwargs):
        """
        添加一次任务
        """
        self.__once.append(asyncio.create_task(fn(*args, **kwargs)))
        return fn

    def once(self, *args, **kwargs):
        """
        一次任务装饰器
        """
        return lambda fn: self.add_once(fn, *args, **kwargs)

    def add_job(self, fn: Coroutine, start: int = 0, interval: int = 5, *args, **kwargs):
        """
        新增任务
        """
        self.__scheduler.add_job(fn, "interval", next_run_time=delta(start), seconds=interval, args=args, kwargs=kwargs)
        return fn

    def job(self, start: int = 0, interval: int = 5, *args, **kwargs):
        """
        新增任务装饰器
        """
        return lambda fn: self.add_job(fn, start=start, interval=interval, *args, **kwargs)
