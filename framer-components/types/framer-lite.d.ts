declare module "framer" {
    export const addPropertyControls: (...args: any[]) => void
    export const ControlType: {
        String: "String"
        Number: "Number"
        Enum: "Enum"
        Boolean: "Boolean"
        Object: "Object"
        Array: "Array"
        File: "File"
        Image: "Image"
        Color: "Color"
    }
}
