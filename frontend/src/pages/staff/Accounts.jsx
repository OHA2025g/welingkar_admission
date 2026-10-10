import { useCallback, useEffect, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { http, errMsg } from "@/lib/api";
import { Card, Empty, PageHeader } from "@/components/portal/ui";
import { useAuth, can } from "@/context/AuthContext";
import { PaymentsTab } from "@/components/finance/PaymentsTab";
import { ExceptionsTab, ReconTab } from "@/components/finance/ReconTab";
import { OfflinePaymentForm } from "@/components/finance/OfflinePaymentForm";
import { DailySheet } from "@/components/finance/DailySheet";

const RecordOffline = ({ onDone }) => {
  const [ref, setRef] = useState("");
  const [amount, setAmount] = useState("");
  return (
    <Card testId="record-offline-card" className="max-w-3xl">
      <p className="mb-1 font-semibold">Record an offline admission-fee payment</p>
      <p className="mb-4 text-xs text-muted-foreground">Proof is mandatory. The amount must equal the configured admission fee; a second payment for the same candidate is blocked.</p>
      <div className="mb-3 grid gap-3 sm:grid-cols-2">
        <Input data-testid="record-offline-app-ref" placeholder="Application reference" value={ref} onChange={(e) => setRef(e.target.value)} />
        <Input data-testid="record-offline-amount" type="number" placeholder="Amount (INR)" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </div>
      <OfflinePaymentForm prefix="accounts" proofRequired modes={["neft", "imps", "upi", "dd", "cheque"]} endpoint="/accounts/payments/offline"
        extra={{ application_ref: ref, amount }} onDone={onDone} />
    </Card>
  );
};

export default function AccountsPage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState("payments");
  const [error, setError] = useState("");
  const load = useCallback(() => http.get("/accounts/payments", { params: { page, page_size: 50 } })
    .then((r) => { setData(r.data); setError(""); })
    .catch((e) => setError(errMsg(e))), [page]);
  useEffect(() => { load(); }, [load]);
  return (
    <div data-testid="accounts-page">
      <PageHeader eyebrow="Finance" title="Payments & reconciliation" description="Online payments are verified with the gateway; offline payments need Accounts verification with proof. Refunds use the Payments console or Cancellations and need a step-up email code." />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="payments" data-testid="accounts-tab-payments">Payment report</TabsTrigger>
          <TabsTrigger value="daily" data-testid="accounts-tab-daily">Daily sheet</TabsTrigger>
          <TabsTrigger value="exceptions" data-testid="accounts-tab-exceptions">Exceptions</TabsTrigger>
          <TabsTrigger value="recon" data-testid="accounts-tab-recon">Reconciliation</TabsTrigger>
          {can(user, "payments.verify") && <TabsTrigger value="offline" data-testid="accounts-tab-offline">Record offline</TabsTrigger>}
        </TabsList>
        <TabsContent value="payments">
          {error && <Empty testId="payments-error" text={`Could not load payments. ${error} If this mentions the gateway, check that Stripe is reachable and try again.`} />}
          {data && <PaymentsTab data={data} onChange={load} page={page} setPage={setPage} />}
        </TabsContent>
        <TabsContent value="daily">{tab === "daily" && <DailySheet />}</TabsContent>
        <TabsContent value="exceptions">{tab === "exceptions" && <ExceptionsTab />}</TabsContent>
        <TabsContent value="recon"><ReconTab /></TabsContent>
        <TabsContent value="offline"><RecordOffline onDone={load} /></TabsContent>
      </Tabs>
    </div>
  );
}
