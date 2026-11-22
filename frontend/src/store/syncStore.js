// import { useCallback } from "react";
// import { useOutputStore } from "./outputStore";

// // Keep store in sync so progress survives remounts
// const syncStore = useCallback((patch) => {
//     useOutputStore.setState((s) => ({
//         output: s.output ? { ...s.output, ...patch } : s.output,
//     }));
// }, []);