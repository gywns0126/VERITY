import { defineConfig, globalIgnores } from "eslint/config"
import nextVitals from "eslint-config-next/core-web-vitals"
import nextTypeScript from "eslint-config-next/typescript"

export default defineConfig([
    ...nextVitals,
    ...nextTypeScript,
    {
        // 기존 클라이언트 터미널은 브라우저 외부 상태(localStorage·실시간 ref)를 effect에서
        // 동기화한다. 전면 구조개편 전에는 React Compiler 권고를 경고로 유지해 lint 자체가
        // 무력화되지 않게 하고, 일반 오류는 계속 실패 처리한다.
        rules: {
            "react-hooks/set-state-in-effect": "warn",
            "react-hooks/refs": "warn",
            "react-hooks/preserve-manual-memoization": "warn",
            "react/no-unescaped-entities": "warn",
            "@next/next/no-html-link-for-pages": "warn",
        },
    },
    globalIgnores([".next/**", "node_modules/**", "next-env.d.ts"]),
])
