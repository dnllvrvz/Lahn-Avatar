import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./index.css";

import LahnAvatarChat from "./App.jsx";
// import VoiceChat from "./VoiceChat.jsx";
import ExperienceUploadPage from "./ExperienceUploadPage.jsx";
// import Mirror from "./Mirror.jsx"
// import Layout from "./Layout.jsx"; // <-- new layout component with sidebar

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>


    <Routes>
      {/*<Route path="/" element={<Layout />}>*/}
      <Route index element={<LahnAvatarChat />} />
      <Route path="chat" element={<LahnAvatarChat />} />
      <Route path="experience" element={<ExperienceUploadPage />} />
      <Route path="*" element={<LahnAvatarChat />} />
      {/*</Route>*/}
    </Routes>
      
    </BrowserRouter>
  </StrictMode>
);




    // <Routes>
    //   <Route index path="/" element={<LahnAvatarChat />} />
    //   <Route path="chat" element={<LahnAvatarChat />} />
    //   <Route path="experience" element={<ExperienceUploadPage />} />
    //   <Route path="*" element={<LahnAvatarChat />} />
    // </Routes>

// {/*<Routes>
// <Route path="/" element={<Layout />}>
//   <Route index element={<LahnAvatarChat />} />  {/* 👈 Default route for "/" */}
//   <Route path="chat" element={<LahnAvatarChat />} />
//   <Route path="experience" element={<ExperienceUploadPage />} />
//   {/*<Route path="voice-chat" element={<VoiceChat />} />*/}
//   {/*<Route path="/mirror" element={<Mirror />} />*/}
//   <Route path="*" element={<LahnAvatarChat />} />
// </Route>
// </Routes>*/}