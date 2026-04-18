import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TopBar } from "./components/layout/TopBar";
import { Sidebar } from "./components/layout/Sidebar";
import { useAppStore } from "./store/app";

const ProfessionalMode = lazy(() =>
  import("./features/professional/ProfessionalMode").then((m) => ({ default: m.ProfessionalMode }))
);
const StudentMode = lazy(() =>
  import("./features/student/StudentMode").then((m) => ({ default: m.StudentMode }))
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
      refetchOnWindowFocus: true,
    },
  },
});

function Shell() {
  const { mode } = useAppStore();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-900 text-slate-100">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex flex-1 overflow-hidden">
          <Suspense fallback={null}>
            {mode === "professional" ? <ProfessionalMode /> : <StudentMode />}
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Shell />
    </QueryClientProvider>
  );
}
