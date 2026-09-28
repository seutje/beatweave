export const joinList = (values: string[]) => values.join(", ");

export const splitList = (value: string) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
