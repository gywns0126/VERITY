declare module "react" {
    export type ReactNode = any
    export type SetStateAction<S> = S | ((prevState: S) => S)
    export type Dispatch<A> = (value: A) => void

    export interface RefObject<T> {
        current: T | null
    }

    export interface CSSProperties {
        [key: string]: string | number | undefined
    }

    export function useState<T = any>(initial: T): [T, Dispatch<SetStateAction<T>>]
    export function useEffect(effect: (...args: any[]) => any, deps?: any[]): void
    export function useMemo<T>(factory: () => T, deps: any[]): T
    export function useRef<T = any>(initial?: T | null): RefObject<T>
    export function useCallback<T extends (...args: any[]) => any>(cb: T, deps: any[]): T

    const React: {
        createElement: any
        Fragment: any
        useState: typeof useState
        useEffect: typeof useEffect
        useMemo: typeof useMemo
        useRef: typeof useRef
        useCallback: typeof useCallback
    }
    export default React
}

declare namespace React {
    type ReactNode = any
    interface CSSProperties {
        [key: string]: string | number | undefined
    }
}
