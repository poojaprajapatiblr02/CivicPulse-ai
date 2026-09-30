export const score = (value: number | null | undefined) => value == null ? 'Not available' : value.toFixed(2)
export const number = (value: number) => value.toLocaleString('en-IN')