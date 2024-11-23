from qrcode import QRCode

from submitter import Client, Task
from submitter.adapter.weibo import Weibo


class AliClient(Client):
    def __init__(self, uid: str = "", password: str = "", token: str = "", ping: float = -1):
        super().__init__("http://gin.web-framework-m88s.1990019364850918.cn-hangzhou.fc.devsapp.net", uid, password, token, ping)

    async def register(self) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.54",
            "Referer": "https://www.bilibili.com",
        }
        resp = await self.session.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate", headers=headers)
        result = resp.json()
        qr = QRCode(border=0)
        qr.add_data(result["data"]["url"])
        qr.make()
        qr.print_ascii()
        input("扫描二维码完成登录后按下回车继续注册")
        data = {
            "uid": self.uid,
            "password": self.password,
            "qrcode_key": result["data"]["qrcode_key"],
        }
        if await self.post("/register", json=data) == "success":
            return await self.token(self.uid, self.password)


@AliClient(uid="your_bilibili_uid", password="the_account_password_you_want_to_use_to_submit_blog")
async def main(self: AliClient):
    token = await self.register()
    self.log.info(f"Token[{token}]")

    @AliClient(ping=30, token=token)
    async def ali(self: AliClient):
        async with Weibo(preload=["7198559139"]) as w:
            for mid in w.blogs:
                log = await self.test(
                    blog=w.blogs[mid],
                    task=Task(
                        public=True,
                        enable=True,
                        name="接收测试",
                        method="POST",
                        url="https://httpbin.org/post",
                        body="{{ json . }}",
                        README="接收所有微博",
                    ),
                )
                self.log.info(log)
                break
