import React from "react";

export function Input(props) {
  return (
    <input
      {...props}
      className="w-full rounded-xl border border-white/20 bg-white/10 p-2 
text-white focus:outline-none"
    />
  );
}

