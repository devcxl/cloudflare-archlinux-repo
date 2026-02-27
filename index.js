export default {
  async fetch(request, env) {
    const key = decodeURIComponent(new URL(request.url).pathname.slice(1));
    const object = await env.ARCH_REPO.get(key);

    if (!object) {
      return new Response("Not found", { status: 404 });
    }

    // 获取对象的总大小
    const objectSize = object.size;

    // 处理范围请求
    const range = request.headers.get("Range");
    if (range) {
      // 解析范围请求，格式如 "bytes=0-1023"
      const [, startStr, endStr] = range.match(/bytes=(\d+)-(\d*)/) || [];
      const start = parseInt(startStr, 10);
      const end = endStr ? parseInt(endStr, 10) : objectSize - 1;

      // 验证范围
      if (start < 0 || start >= objectSize) {
        return new Response("Range Not Satisfiable", {
          status: 416,
          headers: { "Content-Range": `bytes */${objectSize}` }
        });
      }

      // 确保结束范围不超过对象大小
      const actualEnd = Math.min(end, objectSize - 1);
      const length = actualEnd - start + 1;

      // 获取范围内容
      const rangeBody = await object.body.slice(start, actualEnd + 1);

      // 返回范围响应
      return new Response(rangeBody, {
        status: 206,
        headers: {
          "Content-Type": object.httpMetadata?.contentType || "application/octet-stream",
          "Cache-Control": "public, max-age=3600",
          "Content-Range": `bytes ${start}-${actualEnd}/${objectSize}`,
          "Content-Length": length.toString(),
          "Accept-Ranges": "bytes",
        },
      });
    }

    // 正常响应（返回整个对象）
    return new Response(object.body, {
      headers: {
        "Content-Type": object.httpMetadata?.contentType || "application/octet-stream",
        "Cache-Control": "public, max-age=3600",
        "Content-Length": objectSize.toString(),
        "Accept-Ranges": "bytes",
      },
    });
  },
};
