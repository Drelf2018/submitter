import asyncio
import datetime
from typing import Coroutine, List, Optional, Tuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bilibili_api import Credential, comment, live

from .data import User
from .network import Api, ApiException


def delta(seconds: float):
    return datetime.datetime.now() + datetime.timedelta(seconds=seconds)


def run_forever(coro: Coroutine, *args, **kwargs):
    loop = asyncio.get_event_loop()
    loop.create_task(coro(*args, **kwargs))
    loop.run_forever()


def stop(err: Exception):
    print(f"{err.__class__.__name__}:", str(err))
    asyncio.get_event_loop().stop()


class Client(Api, Credential):
    """
    客户端层
    
    对 Api 进一步封装
    """
    def __init__(
        self,
        url: str,
        token: str = "",
        sessdata: str | None = None,
        bili_jct: str | None = None,
        dedeuserid: str | None = None,
    ):
        """
        Args:
            url: 基础接口地址
        
            token: 鉴权码

            sessdata: 浏览器 Cookies 中的 SESSDATA 字段值. Defaults to None.

            bili_jct: 浏览器 Cookies 中的 bili_jct 字段值. Defaults to None.

            dedeuserid: 浏览器 Cookies 中的 DedeUserID 字段值. Defaults to None.
        """
        Api.__init__(self, url, token)
        Credential.__init__(self, sessdata=sessdata, bili_jct=bili_jct, dedeuserid=dedeuserid)

    async def check_token_vaild(self) -> Tuple[User, Optional[Exception | ApiException]]:
        """
        鉴权
        """
        data, err = await self.get("/me")
        if err is not None:
            return None, err
        return User(**data), None

    async def get_self_uid(self) -> str:
        """
        获取自身 uid
        """
        info = await live.get_self_info(self)
        return str(info["uid"])

    async def get_self_token(self) -> Tuple[str, Optional[Exception | ApiException]]:
        """
        获取自身鉴权码
        """
        data, err = await self.get("/token", params={"uid": self.dedeuserid})
        if err is not None:
            return "", err
        resp = await comment.send_comment(data["token"], data["oid"], comment.CommentResourceType.DYNAMIC, credential=self)
        if resp["success_action"] != 0:
            return "", ApiException(400, "Send comment failed.")
        await asyncio.sleep(2)  # wait for bilibili update comment
        return await self.register(data["auth"])

    async def login(self, boom: bool = False) -> Optional[Exception | ApiException]:
        """
        登录
        """
        user, err = await self.check_token_vaild()
        if err is not None:
            return err
        if self.dedeuserid is None:
            self.dedeuserid = await self.get_self_uid()
        if user.uid != self.dedeuserid:
            if boom:
                return ApiException(400, "Login failed.")
            self.token, err = await self.get_self_token()
            if err is not None:
                return err
            return self.login(True)  # double check


class Submitter(Client):
    """
    提交器

    use

    ```python
    async def main():
        async with Submitter(url, token) as sub:
            @sub.job(0, 1)
            async def _():
                pass
    
    run_forever(main)
    ```

    or

    ```
    @Submitter(url, token)
    async def _(sub: Submitter):
        @sub.job(0, 1)
        async def _():
            pass
    ```
    """
    async def __run__(self):
        for fn, args, kwargs in self.__once:
                await fn(*args, **kwargs)
        self.__scheduler.start()

    async def __aenter__(self):
        self.__once: List[Tuple[Coroutine, tuple, dict]] = []
        self.__scheduler = AsyncIOScheduler(timezone="Asia/Shanghai", event_loop=asyncio.get_running_loop())
        self.__vaild = await self.login()
        return self

    async def __aexit__(self, typ_, value, trace):
        if typ_ is not None:
            stop(typ_(value))
        elif self.__vaild is not None:
            stop(self.__vaild)
        else:
            await self.__run__()

    def add_job(self, fn: Coroutine, start: int = 0, interval: int = 5, once: bool = False, *args, **kwargs):
        """
        新增任务
        """
        if once:
            self.__once.append((fn, args, kwargs))
        else:
            self.__scheduler.add_job(fn, "interval", next_run_time=delta(start), seconds=interval, args=args, kwargs=kwargs)

    def job(self, start: int = 0, interval: int = 5, once: bool = False, *args, **kwargs):
        """
        新增任务装饰器
        """
        def inner(fn: Coroutine):
            self.add_job(fn, start=start, interval=interval, once=once, *args, **kwargs)
            return fn
        return inner

    def __call__(self, fn: Coroutine):
        async def main():
            await self.__aenter__()
            if self.__vaild is not None:
                stop(self.__vaild)
            else:
                try:
                    await fn(self)
                    await self.__run__()
                except Exception as e:
                    stop(e)
        run_forever(main)