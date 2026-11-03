import test from 'node:test'
import assert from 'node:assert/strict'

import worker from '../index.js'

// 贴近真实 R2 绑定：body 是 ReadableStream（没有 slice），range 由存储层切片。
function createBucket(contents) {
  const calls = []

  function streamOf(bytes) {
    return new ReadableStream({
      start(controller) {
        controller.enqueue(bytes)
        controller.close()
      },
    })
  }

  return {
    calls,
    async head(key) {
      calls.push({ op: 'head', key })
      const value = contents[key]
      if (value === undefined) return null
      return { key, size: value.length }
    },
    async get(key, options) {
      calls.push({ op: 'get', key, range: options?.range })
      const value = contents[key]
      if (value === undefined) return null

      const bytes = new TextEncoder().encode(value)
      const start = options?.range?.offset ?? 0
      const end = options?.range ? start + options.range.length : bytes.length

      return {
        body: streamOf(bytes.slice(start, end)),
        size: bytes.length,
        range: { offset: start, length: end - start },
        httpMetadata: { contentType: 'application/octet-stream' },
      }
    },
  }
}

test('Worker 应直接读取根路径对象', async () => {
  const keys = []
  const env = {
    ARCH_REPO: {
      async get(key) {
        keys.push(key)
        return {
          body: 'ok',
          size: 2,
          httpMetadata: { contentType: 'text/plain' },
        }
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/devcxl.db'), env)

  assert.equal(response.status, 200)
  assert.deepEqual(keys, ['devcxl.db'])
  assert.equal(await response.text(), 'ok')
})

test('Worker 应正确解码路径', async () => {
  const keys = []
  const env = {
    ARCH_REPO: {
      async get(key) {
        keys.push(key)
        return {
          body: 'decoded',
          size: 7,
          httpMetadata: { contentType: 'text/plain' },
        }
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/%E4%B8%AD'), env)

  assert.equal(response.status, 200)
  assert.deepEqual(keys, ['中'])
})

test('对象不存在时返回 404', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        return null
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/devcxl.gpg'), env)

  assert.equal(response.status, 404)
  assert.equal(await response.text(), 'Not found')
})

test('根路径包请求应回退到 packages 目录', async () => {
  const keys = []
  const env = {
    ARCH_REPO: {
      async get(key) {
        keys.push(key)

        if (key === 'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst') {
          return {
            body: 'pkg',
            size: 3,
            httpMetadata: { contentType: 'application/octet-stream' },
          }
        }

        return null
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/localsend-bin-1.0-1-x86_64.pkg.tar.zst'), env)

  assert.equal(response.status, 200)
  assert.deepEqual(keys, [
    'localsend-bin-1.0-1-x86_64.pkg.tar.zst',
    'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst',
  ])
  assert.equal(await response.text(), 'pkg')
})

test('根路径包签名请求应回退到 packages 目录', async () => {
  const keys = []
  const env = {
    ARCH_REPO: {
      async get(key) {
        keys.push(key)

        if (key === 'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig') {
          return {
            body: 'sig',
            size: 3,
            httpMetadata: { contentType: 'application/octet-stream' },
          }
        }

        return null
      },
    },
  }

  const response = await worker.fetch(new Request('https://repo.archlinux.devcxl.cn/localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig'), env)

  assert.equal(response.status, 200)
  assert.deepEqual(keys, [
    'localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig',
    'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig',
  ])
  assert.equal(await response.text(), 'sig')
})

test('合法 Range 返回 206 与正确的 Content-Range / Content-Length', async () => {
  const bucket = createBucket({ file: 'abcd' })

  const response = await worker.fetch(
    new Request('https://repo.dev/file', { headers: { Range: 'bytes=0-1' } }),
    { ARCH_REPO: bucket },
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get('Content-Range'), 'bytes 0-1/4')
  assert.equal(response.headers.get('Content-Length'), '2')
  assert.equal(await response.text(), 'ab')
  assert.deepEqual(bucket.calls.at(-1), { op: 'get', key: 'file', range: { offset: 0, length: 2 } })
})

test('后缀 Range bytes=-N 返回最后 N 字节', async () => {
  const bucket = createBucket({ file: 'abcd' })

  const response = await worker.fetch(
    new Request('https://repo.dev/file', { headers: { Range: 'bytes=-2' } }),
    { ARCH_REPO: bucket },
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get('Content-Range'), 'bytes 2-3/4')
  assert.equal(await response.text(), 'cd')
})

test('开放结尾 Range bytes=N- 正确截断到对象末尾', async () => {
  const bucket = createBucket({ file: 'abcd' })

  const response = await worker.fetch(
    new Request('https://repo.dev/file', { headers: { Range: 'bytes=2-' } }),
    { ARCH_REPO: bucket },
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get('Content-Range'), 'bytes 2-3/4')
  assert.equal(await response.text(), 'cd')
})

test('Range 超出对象大小时收敛到末尾而非失败', async () => {
  const response = await worker.fetch(
    new Request('https://repo.dev/file', { headers: { Range: 'bytes=3-99' } }),
    { ARCH_REPO: createBucket({ file: 'abcd' }) },
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get('Content-Range'), 'bytes 3-3/4')
  assert.equal(await response.text(), 'd')
})

test('非法/不支持的 Range 返回 416 且不读取对象体', async () => {
  for (const range of ['bytes=abc', 'bytes=0-1,2-3', 'bytes=10-20', 'bytes=-']) {
    const bucket = createBucket({ file: 'abcd' })
    const response = await worker.fetch(
      new Request('https://repo.dev/file', { headers: { Range: range } }),
      { ARCH_REPO: bucket },
    )
    assert.equal(response.status, 416, `期望 416 for Range=${range}`)
    assert.equal(response.headers.get('Content-Range'), 'bytes */4')
    assert.ok(!bucket.calls.some((call) => call.op === 'get'), `Range=${range} 不应触发对象读取`)
  }
})

test('Range 请求对不存在对象返回 404', async () => {
  const response = await worker.fetch(
    new Request('https://repo.dev/missing', { headers: { Range: 'bytes=0-1' } }),
    { ARCH_REPO: createBucket({}) },
  )
  assert.equal(response.status, 404)
})

test('Range 请求支持 packages/ 回退', async () => {
  const bucket = createBucket({ 'packages/pkg-1.0-1-x86_64.pkg.tar.zst': 'abcd' })

  const response = await worker.fetch(
    new Request('https://repo.dev/pkg-1.0-1-x86_64.pkg.tar.zst', { headers: { Range: 'bytes=1-2' } }),
    { ARCH_REPO: bucket },
  )
  assert.equal(response.status, 206)
  assert.equal(response.headers.get('Content-Range'), 'bytes 1-2/4')
  assert.equal(await response.text(), 'bc')
})

test('R2 读取异常返回 502', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        throw new Error('r2 down')
      },
      async head() {
        throw new Error('r2 down')
      },
    },
  }

  const full = await worker.fetch(new Request('https://repo.dev/file'), env)
  const ranged = await worker.fetch(
    new Request('https://repo.dev/file', { headers: { Range: 'bytes=0-1' } }),
    env,
  )

  assert.equal(full.status, 502)
  assert.equal(ranged.status, 502)
})

test('畸形 percent-encoding 返回 400 而非 500', async () => {
  const env = {
    ARCH_REPO: {
      async get() {
        return { body: 'x', size: 1, httpMetadata: {} }
      },
      async head() {
        return { key: 'x', size: 1 }
      },
    },
  }

  const response = await worker.fetch(
    new Request('https://repo.dev/%zz'),
    env,
  )
  assert.equal(response.status, 400)
})
