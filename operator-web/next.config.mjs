/** @type {import('next').NextConfig} */
const nextConfig = {
    // 오퍼레이터 전용(비공개). 검색엔진 색인 방지 헤더.
    async headers() {
        return [
            {
                source: "/:path*",
                headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
            },
        ]
    },
}

export default nextConfig
