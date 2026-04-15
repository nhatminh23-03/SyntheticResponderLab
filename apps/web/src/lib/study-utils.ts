// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function isReadyToRun(study: any): boolean {
  return (
    study?.audience?.status === "saved" &&
    study?.survey?.status === "saved" &&
    study?.experiment?.status === "saved"
  );
}
