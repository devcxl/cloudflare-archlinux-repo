const PACKAGE_ARTIFACT_PATTERN = /\.pkg\.tar\.zst(?:\.sig)?$/

function isPackageArtifact(pathname) {
  return PACKAGE_ARTIFACT_PATTERN.test(pathname)
}

// 候选 key：优先原始路径，包产物再回退到 packages/ 前缀（兼容历史存储布局）。
function candidateKeys(key) {
  if (isPackageArtifact(key) && !key.startsWith('packages/')) {
    return [key, `packages/${key}`]
  }
  return [key]
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

function responseHeaders(object, extra) {
  return {
    'Content-Type': object.httpMetadata?.contentType || 'application/octet-stream',
    'Cache-Control': 'public, max-age=3600',
    'Accept-Ranges': 'bytes',
    ...extra,
  }
}

// Range 请求需要先拿到完整对象大小才能校验范围并拼出 Content-Range；
// R2 的 range 选项交由存储层切片，body 是 ReadableStream，不能在 Worker 侧 slice。
async function resolveObject(env, key) {
  for (const candidate of candidateKeys(key)) {
    const head = await env.ARCH_REPO.head(candidate)
    if (head) return { key: candidate, size: head.size }
  }
  return null
}

async function readObject(env, key) {
  for (const candidate of candidateKeys(key)) {
    const object = await env.ARCH_REPO.get(candidate)
    if (object) return object
  }
  return null
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

    const range = request.headers.get('Range')

    if (!range) {
      let object
      try {
        object = await readObject(env, key)
      } catch {
        return new Response('Bad Gateway', { status: 502 })
      }

      if (!object) {
        return new Response('Not found', { status: 404 })
      }

      return new Response(object.body, {
        headers: responseHeaders(object, {
          'Content-Length': object.size.toString(),
        }),
      })
    }

    let resolved
    try {
      resolved = await resolveObject(env, key)
    } catch {
      return new Response('Bad Gateway', { status: 502 })
    }

    if (!resolved) {
      return new Response('Not found', { status: 404 })
    }

    const parsed = parseRange(range, resolved.size)
    if (!parsed) {
      return new Response('Range Not Satisfiable', {
        status: 416,
        headers: {
          'Content-Range': `bytes */${resolved.size}`,
          'Accept-Ranges': 'bytes',
        },
      })
    }

    const { start, end, length } = parsed

    let object
    try {
      object = await env.ARCH_REPO.get(resolved.key, { range: { offset: start, length } })
    } catch {
      return new Response('Bad Gateway', { status: 502 })
    }

    if (!object?.body) {
      return new Response('Bad Gateway', { status: 502 })
    }

    return new Response(object.body, {
      status: 206,
      headers: responseHeaders(object, {
        'Content-Range': `bytes ${start}-${end}/${resolved.size}`,
        'Content-Length': length.toString(),
      }),
    })
  },
}
