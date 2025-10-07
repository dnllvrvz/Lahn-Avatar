import React from "react";

export function Card({ children }) {
  return (
    <div className="rounded-2xl bg-white/10 p-4 shadow-lg 
backdrop-blur-md">
      {children}
    </div>
  );
}

export function CardContent({ children }) {
  return <div className="p-4">{children}</div>;
}

