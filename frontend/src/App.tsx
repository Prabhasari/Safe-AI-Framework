import { BrowserRouter, Routes, Route } from "react-router-dom";
import SecureGenerator from "./pages/SecureGenerator";
import CoreSystemUploader from "./pages/CoreSystemUploader"
import PluginStudioPage from "./pages/PluginStudioPage";
// If you already had a Home component, keep it. Here is a tiny placeholder:
// function Home() {
//   return (
//     <div style={{ padding: 24 }}>
//       <h2>SAFE-AI-FRAMEWORK</h2>
//       <p>Welcome. Open the Secure Generator from the link below.</p>
//       <Link to="/secure-generator">Go to Secure Generator →</Link>
//     </div>
//   );
// }

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<CoreSystemUploader />} />
        <Route path="/CoreSystemUploader" element={<CoreSystemUploader />} />
        <Route path="/secure-generator" element={<SecureGenerator />} />
        <Route path="/PluginStudioPage" element={<PluginStudioPage />} />

      </Routes>
    </BrowserRouter>
  );
}
