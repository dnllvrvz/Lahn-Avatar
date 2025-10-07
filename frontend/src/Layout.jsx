import { Outlet, Link, useLocation } from "react-router-dom";
import { useState } from "react";
import { Menu, X } from "lucide-react";

export default function Layout() {
  const { pathname } = useLocation();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="flex h-screen font-sans overflow-hidden min-h-0">
      {/* Hamburger button */}
      {!isOpen && (
        <button
          className="p-2 m-2 bg-white rounded-md shadow-md z-10"
          onClick={() => setIsOpen(true)}
        >
          <Menu size={24} />
        </button>
      )}

      {/* Sidebar navigation */}
      <nav
        className={
          `
            fixed top-0 left-0 h-full w-64 bg-gradient-to-b from-emerald-100 to-stone-100 p-5 shadow-md
            transform transition-transform duration-200 ease-in-out
            ${isOpen ? "translate-x-0" : "-translate-x-full"}
            flex flex-col gap-4
          `
        }
      >
        {/* Close icon inside sidebar */}
        <button
          className="self-end mb-4 p-2 text-stone-700 hover:text-stone-900"
          onClick={() => setIsOpen(false)}
        >
          <X size={20} />
        </button>
        <h2 className="text-2xl font-semibold text-stone-700 mb-6">🌊 Lahn Avatar</h2>

        <Link
          to="/chat"
          onClick={() => setIsOpen(false)}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            pathname === "/chat"
              ? "bg-amber-300 text-amber-900"
              : "text-stone-700 hover:bg-amber-100 hover:text-amber-900"
          }`}
        >
          🧠 Chat with the River
        </Link>
        {/*<Link
          to="/voice-chat"
          onClick={() => setIsOpen(false)}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            pathname === "/voice-chat"
              ? "bg-amber-300 text-amber-900"
              : "text-stone-700 hover:bg-amber-100 hover:text-amber-900"
          }`}
        >
          🗣 Voice Chat
        </Link>*/}
        <Link
          to="/experience"
          onClick={() => setIsOpen(false)}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            pathname === "/experience"
              ? "bg-amber-300 text-amber-900"
              : "text-stone-700 hover:bg-amber-100 hover:text-amber-900"
          }`}
        >
          ✍️ Share Experience
        </Link>
        {/*<Link
          to="/mirror"
          onClick={() => setIsOpen(false)}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            pathname === "/mirror"
              ? "bg-amber-300 text-amber-900"
              : "text-stone-700 hover:bg-amber-100 hover:text-amber-900"
          }`}
        >
          🪞 Mirror
        </Link>*/}
      </nav>

      {/* Main content */}
      <main className={`flex-1 p-8 bg-gradient-to-br from-stone-50 to-green-50 transition-margin duration-200 ${isOpen ? 'ml-64' : 'ml-0'} overflow-hidden min-h-0`}>
        <Outlet />
      </main>
    </div>
  );
}
