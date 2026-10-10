import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import { RequireCandidate, RequirePerm, RequireStaff } from "@/components/portal/Guards";
import StaffShell from "@/components/portal/StaffShell";
import Console from "@/pages/Console";
import PaymentReturn from "@/pages/PaymentReturn";
import Landing from "@/pages/Landing";
import StaffLogin from "@/pages/StaffLogin";
import CandidateLogin from "@/pages/CandidateLogin";
import CandidateRegister from "@/pages/CandidateRegister";
import ForgotPassword from "@/pages/ForgotPassword";
import CandidateDashboard from "@/pages/CandidateDashboard";
import StaffDashboard from "@/pages/staff/Dashboard";
import UsersPage from "@/pages/staff/Users";
import RolesPage from "@/pages/staff/Roles";
import CyclesPage from "@/pages/staff/Cycles";
import ProgramsPage from "@/pages/staff/Programs";
import PoliciesPage from "@/pages/staff/Policies";
import AuditPage from "@/pages/staff/Audit";
import CandidatesPage from "@/pages/staff/Candidates";
import ModulePlaceholder from "@/pages/staff/ModulePlaceholder";
import ApplicationsPage from "@/pages/staff/Applications";
import ApplicationDetail from "@/pages/staff/ApplicationDetail";
import PartADashboard from "@/pages/staff/PartADashboard";
import CandidateShell from "@/components/candidate/CandidateShell";
import AdmissionInfo from "@/pages/candidate/AdmissionInfo";
import ApplicationPage from "@/pages/candidate/Application";
import FeePage from "@/pages/candidate/Fee";
import PostSubmission from "@/pages/candidate/PostSubmission";
import AccessDenied from "@/pages/AccessDenied";
import InterviewsPage from "@/pages/staff/Interviews";
import InterviewSession from "@/pages/staff/InterviewSession";
import ScoringPage from "@/pages/staff/Scoring";
import ScoringSession from "@/pages/staff/ScoringSession";
import ResultsPage from "@/pages/staff/Results";
import ResultVersion from "@/pages/staff/ResultVersion";
import EvaluationsPage from "@/pages/staff/Evaluations";
import CandidateInterview from "@/pages/candidate/Interview";
import CandidateResults from "@/pages/candidate/Results";
import CandidatePartB from "@/pages/candidate/PartB";
import PartBImports from "@/pages/staff/PartBImports";
import PartBCandidates from "@/pages/staff/PartBCandidates";
import AllotmentPage from "@/pages/staff/Allotment";
import AllotmentBatch from "@/pages/staff/AllotmentBatch";
import VerificationPage from "@/pages/staff/Verification";
import VerificationCandidate from "@/pages/staff/VerificationCandidate";
import AdmissionFeePage from "@/pages/candidate/AdmissionFee";
import CancellationPage from "@/pages/candidate/Cancellation";
import AccountsPage from "@/pages/staff/Accounts";
import CancellationsPage from "@/pages/staff/Cancellations";
import PrintCentre from "@/pages/staff/PrintCentre";
import Candidate360 from "@/pages/staff/Candidate360";
import DownloadPage from "@/pages/staff/Download";
import ReportsPage from "@/pages/staff/Reports";

const P = (perm, el) => <RequirePerm perm={perm}>{el}</RequirePerm>;

function App() {
  return (
    <div className="App min-h-screen">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/candidate/login" element={<CandidateLogin />} />
            <Route path="/candidate/register" element={<CandidateRegister />} />
            <Route path="/candidate/forgot-password" element={<ForgotPassword />} />
            <Route path="/candidate" element={<RequireCandidate><CandidateShell /></RequireCandidate>}>
              <Route path="dashboard" element={<CandidateDashboard />} />
              <Route path="admission-info" element={<AdmissionInfo />} />
              <Route path="application" element={<ApplicationPage />} />
              <Route path="payment" element={<FeePage />} />
              <Route path="payment/success" element={<FeePage outcome="success" />} />
              <Route path="payment/cancel" element={<FeePage outcome="cancel" />} />
              <Route path="after-submission" element={<PostSubmission />} />
              <Route path="interviews" element={<CandidateInterview />} />
              <Route path="results" element={<CandidateResults />} />
              <Route path="part-b" element={<CandidatePartB />} />
              <Route path="admission-fee" element={<AdmissionFeePage />} />
              <Route path="admission-fee/success" element={<AdmissionFeePage outcome="success" />} />
              <Route path="admission-fee/cancel" element={<AdmissionFeePage outcome="cancel" />} />
              <Route path="cancellation" element={<CancellationPage />} />
            </Route>
            <Route path="/login" element={<Navigate to="/candidate/login" replace />} />
            <Route path="/register" element={<Navigate to="/candidate/register" replace />} />
            <Route path="/staff/login" element={<StaffLogin />} />
            <Route path="/staff" element={<RequireStaff><StaffShell /></RequireStaff>}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<StaffDashboard />} />
              <Route path="users" element={P("users.manage", <UsersPage />)} />
              <Route path="roles" element={P("roles.read", <RolesPage />)} />
              <Route path="cycles" element={P("cycles.read", <CyclesPage />)} />
              <Route path="programs" element={P("programs.read", <ProgramsPage />)} />
              <Route path="policies" element={P("policies.read", <PoliciesPage />)} />
              <Route path="candidates" element={P("candidates.read", <CandidatesPage />)} />
              <Route path="candidates/:id" element={P("candidates.read", <Candidate360 />)} />
              <Route path="accounts" element={P("payments.read", <AccountsPage />)} />
              <Route path="cancellations" element={P(["cancellations.review", "payments.read", "partb.read"], <CancellationsPage />)} />
              <Route path="print" element={P("print.center", <PrintCentre />)} />
              <Route path="download" element={P("users.manage", <DownloadPage />)} />
              <Route path="audit" element={P("audit.read", <AuditPage />)} />
              <Route path="part-a" element={P("applications.read", <PartADashboard />)} />
              <Route path="applications" element={P("applications.read", <ApplicationsPage />)} />
              <Route path="applications/:id" element={P("applications.read", <ApplicationDetail />)} />
              <Route path="interviews" element={P("interviews.manage", <InterviewsPage />)} />
              <Route path="interviews/sessions/:id" element={P("interviews.manage", <InterviewSession />)} />
              <Route path="scoring" element={P("assessments.score", <ScoringPage />)} />
              <Route path="scoring/:id" element={P("assessments.score", <ScoringSession />)} />
              <Route path="evaluations" element={P("evaluations.read", <EvaluationsPage />)} />
              <Route path="results" element={P("results.read", <ResultsPage />)} />
              <Route path="results/:version" element={P("results.read", <ResultVersion />)} />
              <Route path="partb-imports" element={P("partb.import", <PartBImports />)} />
              <Route path="partb-candidates" element={P("partb.read", <PartBCandidates />)} />
              <Route path="allotment" element={P("partb.read", <AllotmentPage />)} />
              <Route path="allotment/:id" element={P("partb.read", <AllotmentBatch />)} />
              <Route path="verification" element={P("documents.verify", <VerificationPage />)} />
              <Route path="verification/:id" element={P("documents.verify", <VerificationCandidate />)} />
              <Route path="reports" element={P("reports.read", <ReportsPage />)} />
              <Route path="modules/reports" element={<Navigate to="/staff/reports" replace />} />
              <Route path="modules/:module" element={<ModulePlaceholder />} />
              <Route path="*" element={<AccessDenied />} />
            </Route>
            <Route path="/poc" element={<RequireStaff>{P("payments.read", <Console />)}</RequireStaff>} />
            <Route path="/payment/success" element={<RequireStaff><PaymentReturn outcome="success" /></RequireStaff>} />
            <Route path="/payment/cancel" element={<RequireStaff><PaymentReturn outcome="cancel" /></RequireStaff>} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
      <Toaster position="top-right" richColors />
    </div>
  );
}

export default App;
