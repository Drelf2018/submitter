import asyncio

from submitter import Weibo


async def main():
    wb = Weibo()
    async for p in wb.posts(7198559139):
        async for c in wb.comments(p):
            print(c)
            break
        break
    
asyncio.run(main())