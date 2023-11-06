from io import BytesIO
from typing import Any, List, Optional, Tuple

import httpx
from loguru import logger
from PIL import Image

from . import settings
from .data import Job, Online, Post, User

HEADERS = {
    "Connection": "keep-alive",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36",
}


class ApiException(Exception):
    """
    接口访问错误
    """
    def __init__(self, url: str, code: int, message: str, **kwargs):
        super().__init__(message)
        self.url = url
        self.code = code
        self.message = message
        self.kwargs = kwargs

    def __str__(self):
        return f"ApiException({self.url}, {self.code}, {self.message})"


class Session:
    """
    会话类
    
    基于 `httpx.AsyncClient`

    参考 `golang` 中错误处理方式
    """
    def __init__(self, url: str, headers: Optional[dict] = None) -> None:
        """
        Args:
            url: 基础接口地址
        
            headers: 自定义请求头
        """
        self.__session = httpx.AsyncClient(base_url=url)
        if headers is None:
            self.headers = HEADERS.copy()
        else:
            self.headers = headers

    def check_code(self, url: str, result: Any) -> Optional[ApiException]:
        if result["code"] != 0:
            return ApiException(url=url, **result)
        return None

    def data(self, result: dict) -> Any:
        return result.get("data")

    @property
    def session(self):
        return self.__session

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        *args,
        **kwargs
    ) -> Tuple[Any, Optional[Exception | ApiException]]:
        # prepare
        if headers is None:
            headers = self.headers
        # fetch
        try:
            if settings.DEBUG:
                logger.debug(f"\n{method} {url}\n  args: {args}\n  kwargs: {kwargs}\n  headers: {headers}")
            resp = await self.__session.request(method, url, headers=headers, *args, **kwargs)
            # if settings.DEBUG:
            #     logger.debug(resp.content)
            if resp.status_code != 200:
                return None, ApiException(url, resp.status_code, f"<Response [{resp.status_code}]>")
            result = resp.json()
        except Exception as e:
            return None, e
        # data
        err = self.check_code(url, result)
        if err is not None:
            return None, err
        return self.data(result), None

    async def get(self, url: str, headers: Optional[dict] = None, *args, **kwargs):
        return await self.request("GET", url, headers, *args, **kwargs)
    
    async def post(self, url: str, headers: Optional[dict] = None, *args, **kwargs):
        return await self.request("POST", url, headers, *args, **kwargs)
    
    async def must_get(self, url: str, headers: Optional[dict] = None, *args, **kwargs):
        return (await self.get(url, headers, *args, **kwargs))[0]
    
    async def must_post(self, url: str, headers: Optional[dict] = None, *args, **kwargs):
        return (await self.post(url, headers, *args, **kwargs))[0]
    

class Api(Session):
    """
    Api 实现层
    """
    def __init__(self, url: str, auth: str):
        """
        Args:
            url: 基础接口地址
        
            auth: 鉴权码
        """
        self.auth = auth
        Session.__init__(self, url, {"Authorization": auth})

    def set_auth(self, auth: str):
        """
        更新鉴权码
        """
        self.auth = auth
        self.headers["Authorization"] = auth

    async def version(self) -> str:
        """
        获取服务端版本
        """
        return await self.must_get("/version")

    async def list(self) -> Tuple[List[str], Optional[Exception | ApiException]]:
        """
        查看资源目录
        """
        return await self.get("/list")

    async def fetch(self, url: str) -> Tuple[bytes, Optional[ApiException]]:
        """
        解析图片网址并返回文件
        """
        resp = await self.session.get(f"/fetch/{url}")
        err = None if resp.status_code == 200 else ApiException(url, resp.status_code, f"<Response [{resp.status_code}]>")
        return resp.content, err

    @staticmethod
    def open(data: bytes) -> Image.Image:
        """
        打开图片
        """
        return Image.open(BytesIO(data))

    async def online(self) -> Tuple[Optional[Online], Optional[Exception | ApiException]]:
        """
        获取当前在线状态
        """
        resp, err = await self.get("/online")
        if err is not None:
            return None, err
        return Online(**resp), None

    async def token(self, uid: str) -> Tuple[dict, Optional[Exception | ApiException]]:
        """
        获取注册所需 Token
        """
        return await self.get("/token", params={"uid": uid})

    async def register(self, auth: str):
        """
        注册或获取鉴权码
        """
        return await self.get("/register", headers={"Authorization": auth})

    async def posts(self, begin: int = None, end: int = None) -> List[Post]:
        """
        查询博文
        """
        params = {}
        if begin is not None:
            params["begin"] = begin
        if end is not None:
            params["end"] = end
        resp, err = await self.get("/posts", params=params)
        if err is not None:
            return []
        return [Post.parse(v) for v in resp["posts"]]

    async def branches(self):
        """
        查询某博文不同版本
        """
        return await self.get("/branches/:platform/:mid")

    async def comments(self):
        """
        查询某博文的评论
        """
        return await self.get("/comments/:platform/:mid")

    async def log(self) -> Tuple[List[str], Optional[Exception | ApiException]]:
        """
        读取日志
        """
        return await self.get("/log")

    async def ping(self):
        """
        更新自身在线状态
        """
        await self.get("/ping")
    
    async def me(self) -> Tuple[User, Optional[Exception | ApiException]]:
        """
        获取自身信息
        """
        data, err = await self.get("/me")
        if err is not None:
            return User(0, 0), err
        return User(**data), None

    async def update(self):
        """
        主动更新主页
        """
        return await self.get("/update")

    async def modify(self, listen: List[str]) -> Tuple[List[str], Optional[Exception | ApiException]]:
        """
        更新监听列表
        """
        return await self.get("/modify", params={"listen": listen})

    async def add(self, job: Job) -> Tuple[List[Job], Optional[Exception | ApiException]]:
        """
        新增任务
        """
        resp, err = await self.post("/add", data=job.json)
        if err is not None:
            return None, err
        return [Job(**job) for job in resp], None

    async def remove(self, jobs: List[str]) -> Tuple[List[Job], Optional[Exception | ApiException]]:
        """
        移除任务
        """
        resp, err = await self.get("/remove", params={"jobs": jobs})
        if err is not None:
            return None, err
        return [Job(**job) for job in resp], None
    
    async def test(self, jobs: List[str]) -> Tuple[List[Job], Optional[Exception | ApiException]]:
        """
        测试任务
        """
        return await self.get("/test", params={"jobs": jobs})

    async def submit(self, post: Post):
        """
        提交博文
        """
        return (await self.post("/submit", data=post.json))[1]

    async def exec(self, cmd: str) -> Tuple[List[str], Optional[Exception | ApiException]]:
        """
        执行命令
        """
        return await self.get(f"/exec/{cmd}")

    async def users(self) -> List[User]:
        """
        获取所有用户
        """
        resp, err = await self.get("/users")
        if err is not None:
            logger.error(err)
            return []
        return [User(**u) for u in resp]

    async def permission(self, uid: str, perm: float):
        """
        修改权限
        """
        return (await self.get(f"/permission/{uid}/{perm}"))[1]

    async def close(self) -> str:
        """
        结束进程
        """
        return await self.must_get("/close")
    
    async def clear(self) -> str:
        """
        删除资源
        """
        return await self.must_get("/clear")
    
    async def reboot(self) -> str:
        """
        删库重启
        """
        return await self.must_get("/reboot")
    
    async def files(self) -> Tuple[Optional[str], Optional[Exception | ApiException]]:
        """
        检查资源
        """
        return await self.get("/files")
    