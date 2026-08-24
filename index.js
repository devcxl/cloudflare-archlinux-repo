const PACKAGE_ARTIFACT_PATTERN = /\.pkg\.tar\.zst(?:\.sig)?$/

function isPackageArtifact(pathname) {
  return PACKAGE_ARTIFACT_PATTERN.test(pathname)
}

// 解析 HTTP Range 头，返回 { start, end, length } 或 null（非法/不支持的范围）。
// 仅支持单段范围；支持 `bytes=N-`（开放结尾）与 `bytes=-N`（后缀范围）。
// 多段范围（含逗号）与无法解析的形式一律视为非法，交由调用方返回 416。
function parseRange(range, objectSize) {
  const m = /^bytes=(\d*)-(\d*)$/.exec(range)
  if (!m) return null

  const startStr = m[1]
  const endStr = m[2]

  let start
  let end

  if (startStr === '') {
    // 后缀范围：bytes=-N（最后 N 字节）
    if (endStr === '') return null
    const suffix = parseInt(endStr, 10)
    if (!Number.isFinite(suffix) || suffix < 0) return null
    start = Math.max(0, objectSize - suffix)
    end = objectSize - 1
  } else {
    start = parseInt(startStr, 10)
    if (!Number.isFinite(start) || start < 0) return null
    end = endStr === '' ? objectSize - 1 : parseInt(endStr, 10)
    if (!Number.isFinite(end) || end < 0) return null
    if (end > objectSize - 1) end = objectSize - 1
  }

  if (start > end || start >= objectSize) return null
  return { start, end, length: end - start + 1 }
}

export default {
  async fetch(request, env) {
    let key
    try {
      key = decodeURIComponent(new URL(request.url).pathname.slice(1))
    } catch {
      // 畸形 percent-encoding（如 /%zz）应返回 400，而非 500
      return new Response('Bad Request', { status: 400 })
    }

    let object
    try {
      object = await env.ARCH_REPO.get(key)
    } catch {
      return new Response('Bad Gateway', { status: 502 })
    }

    if (!object && isPackageArtifact(key) && !key.startsWith('packages/')) {
      try {
        object = await env.ARCH_REPO.get(`packages/${key}`)
      } catch {
        return new Response('Bad Gateway', { status: 502 })
      }
    }

    if (!object) {
      return new Response('Not found', { status: 404 })
    }

    const objectSize = object.size
    const range = request.headers.get('Range')

    if (range) {
      const parsed = parseRange(range, objectSize)
      if (!parsed) {
        return new Response('Range Not Satisfiable', {
          status: 416,
          headers: { 'Content-Range': `bytes */${objectSize}` },
        })
      }

      const { start, end, length } = parsed

      let rangeBody
      try {
        rangeBody = await object.body.slice(start, end + 1)
      } catch {
        return new Response('Bad Gateway', { status: 502 })
      }

      return new Response(rangeBody, {
        status: 206,
        headers: {
          'Content-Type': object.httpMetadata?.contentType || 'application/octet-stream',
          'Cache-Control': 'public, max-age=3600',
          'Content-Range': `bytes ${start}-${end}/${objectSize}`,
          'Content-Length': length.toString(),
          'Accept-Ranges': 'bytes',
        },
      })
    }

    return new Response(object.body, {
      headers: {
        'Content-Type': object.httpMetadata?.contentType || 'application/octet-stream',
        'Cache-Control': 'public, max-age=3600',
        'Content-Length': objectSize.toString(),
        'Accept-Ranges': 'bytes',
      },
    })
  },
}
