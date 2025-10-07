import React from "react";

export function Button({ children, ...props }) {
  return (
    <button
      {...props}
      className="rounded-xl bg-blue-500 px-4 py-2 text-white 
hover:bg-blue-600 transition-all"
    >
      {children}
    </button>
  );
}

