import {
  FileUp,
  ShieldAlert,
  MessageSquare,
  BookOpen,
  GitGraph,
  PenLine,
} from "lucide-react";
import { ChatPanel } from "./ChatPanel";
import { DocumentUpload } from "./DocumentUpload";
import { RiskReportPanel } from "./RiskReportPanel";
import { ResearchSidebar } from "./ResearchSidebar";
import { CitationGraph } from "./CitationGraph";
import { DraftingPanel } from "./DraftingPanel";
import { useAppStore } from "../../store/app";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";

export function ProfessionalMode() {
  const {
    activeProfessionalTab: tab,
    setActiveProfessionalTab: setTab,
    researchSidebarOpen,
    toggleResearchSidebar,
    citationGraphOpen,
    setCitationGraphOpen,
    draftingPanelOpen,
    toggleDraftingPanel,
  } = useAppStore();

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-1 border-b border-slate-700 bg-slate-900 px-3 py-1.5">
          <TabButton active={tab === "chat"} onClick={() => setTab("chat")} icon={<MessageSquare className="h-3.5 w-3.5" />}>
            Chat
          </TabButton>
          <TabButton active={tab === "upload"} onClick={() => setTab("upload")} icon={<FileUp className="h-3.5 w-3.5" />}>
            Documents
          </TabButton>
          <TabButton active={tab === "risk"} onClick={() => setTab("risk")} icon={<ShieldAlert className="h-3.5 w-3.5" />}>
            Risk Report
          </TabButton>

          <div className="ml-auto flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={toggleResearchSidebar}
              className={cn(researchSidebarOpen && "bg-slate-700 text-slate-200")}
              title="Legal Research"
            >
              <BookOpen className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setCitationGraphOpen(true)}
              title="Citation Graph"
            >
              <GitGraph className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={toggleDraftingPanel}
              className={cn(draftingPanelOpen && "bg-slate-700 text-slate-200")}
              title="Drafting Panel"
            >
              <PenLine className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* Tab content — all panels stay mounted so local state is preserved across tab switches */}
        <div className="relative flex-1 overflow-y-auto">
          <div className={cn("h-full", tab !== "chat" && "hidden")}><ChatPanel /></div>
          <div className={cn("p-6 max-w-xl mx-auto pt-8", tab !== "upload" && "hidden")}>
            <h2 className="text-sm font-semibold text-slate-300 mb-4">Upload Document</h2>
            <DocumentUpload onUploaded={() => setTab("risk")} />
          </div>
          <div className={cn("p-4", tab !== "risk" && "hidden")}><RiskReportPanel /></div>
        </div>
      </div>

      {/* Research sidebar */}
      <ResearchSidebar />

      {/* Overlays */}
      {citationGraphOpen && <CitationGraph />}
      {draftingPanelOpen && <DraftingPanel />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors",
        active
          ? "bg-slate-700 text-slate-100"
          : "text-slate-500 hover:text-slate-300",
      )}
    >
      {icon}
      {children}
    </button>
  );
}
