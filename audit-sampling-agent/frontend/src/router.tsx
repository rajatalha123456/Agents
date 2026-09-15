import { createBrowserRouter } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Engagements } from "./pages/Engagements";
import { EngagementDetail } from "./pages/EngagementDetail";
import { DatasetUpload } from "./pages/DatasetUpload";
import { SchemaMapping } from "./pages/SchemaMapping";
import { PolicyEditor } from "./pages/PolicyEditor";
import { RulePackEditor } from "./pages/RulePackEditor";
import { RunLauncher } from "./pages/RunLauncher";
import { RunProgress } from "./pages/RunProgress";
import { RiskDashboard } from "./pages/RiskDashboard";
import { TransactionExplorer } from "./pages/TransactionExplorer";
import { ItemDetail } from "./pages/ItemDetail";
import { SampleReview } from "./pages/SampleReview";
import { TestingWorksheet } from "./pages/TestingWorksheet";
import { Evaluation } from "./pages/Evaluation";
import { ChallengeCenter } from "./pages/ChallengeCenter";
import { Benchmark } from "./pages/Benchmark";
import { AuditTrailViewer } from "./pages/AuditTrailViewer";
import { Admin } from "./pages/Admin";
import { NotFound } from "./pages/NotFound";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "engagements", element: <Engagements /> },
      { path: "engagements/:engagementId", element: <EngagementDetail /> },
      { path: "datasets/upload", element: <DatasetUpload /> },
      { path: "datasets/:datasetId/schema-mapping", element: <SchemaMapping /> },
      { path: "policies/new", element: <PolicyEditor /> },
      { path: "rule-packs", element: <RulePackEditor /> },
      { path: "runs/launch", element: <RunLauncher /> },
      { path: "runs/:runId/progress", element: <RunProgress /> },
      { path: "runs/:runId/risk-dashboard", element: <RiskDashboard /> },
      { path: "runs/:runId/transactions", element: <TransactionExplorer /> },
      { path: "runs/:runId/items/:itemId", element: <ItemDetail /> },
      { path: "runs/:runId/sample", element: <SampleReview /> },
      { path: "runs/:runId/testing", element: <TestingWorksheet /> },
      { path: "runs/:runId/evaluation", element: <Evaluation /> },
      { path: "runs/:runId/challenge", element: <ChallengeCenter /> },
      { path: "runs/:runId/benchmark", element: <Benchmark /> },
      { path: "audit-trail", element: <AuditTrailViewer /> },
      { path: "admin", element: <Admin /> },
      { path: "*", element: <NotFound /> },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
