"use client";

import { useCallback, useEffect, useState } from "react";
import { useAppRuntime } from "@/app/components/runtime/AppRuntimeProvider";
import {
  adminListUsers,
  adminListRequests,
  adminListHistory,
  adminApproveRequest,
  adminListPendingUsers,
  adminApproveUser,
  type AdminUser,
  type AdminRequest,
  type AdminHistory,
  type AdminPendingUser,
} from "@/app/lib/client/admin-adapter";

interface AdminModalProps {
  onClose: () => void;
  onPendingCountChange?: (count: number) => void;
}

function SectionLoading() {
  return <p className="admin-modal__list-empty">加载中…</p>;
}

interface UserRowProps {
  user: AdminUser;
}

function UserRow({ user }: UserRowProps) {
  return (
    <li className="admin-modal__row admin-modal__row--user">
      <span className="admin-modal__cell admin-modal__cell--account" title={user.account}>{user.account}</span>
      <span className="admin-modal__cell admin-modal__cell--node" title={user.nodeName}>{user.nodeName}</span>
      <span className="admin-modal__cell admin-modal__cell--count">{user.fileCount} 篇</span>
      <span className={`admin-modal__badge${user.nodeType === "中心节点" ? " admin-modal__badge--center" : ""}`}>
        {user.nodeType}
      </span>
    </li>
  );
}

interface PendingUserRowProps {
  user: AdminPendingUser;
  onDecide: (id: number, approved: boolean) => void;
  busyKey: string | null;
}

function PendingUserRow({ user, onDecide, busyKey }: PendingUserRowProps) {
  const approveKey = `u${user.id}:1`;
  const rejectKey = `u${user.id}:0`;
  const busy = busyKey !== null;
  return (
    <li className="admin-modal__row admin-modal__row--pending">
      <span className="admin-modal__cell admin-modal__cell--account" title={user.account}>{user.account}</span>
      <span className="admin-modal__cell admin-modal__cell--node" title={user.email || "未填写邮箱"}>
        {user.email || <em className="admin-modal__empty-remark">未填写</em>}
      </span>
      <span className="admin-modal__cell admin-modal__cell--date">{user.createdAt}</span>
      <span className="admin-modal__pending-actions">
        <button
          type="button"
          className={`admin-modal__approve-btn${busyKey === approveKey ? " is-loading" : ""}`}
          disabled={busy}
          onClick={() => onDecide(user.id, true)}
          aria-busy={busyKey === approveKey}
        >
          {busyKey === approveKey ? "处理中…" : "通过"}
        </button>
        <button
          type="button"
          className={`admin-modal__reject-btn${busyKey === rejectKey ? " is-loading" : ""}`}
          disabled={busy}
          onClick={() => onDecide(user.id, false)}
          aria-busy={busyKey === rejectKey}
        >
          {busyKey === rejectKey ? "处理中…" : "拒绝"}
        </button>
      </span>
    </li>
  );
}

interface RequestRowProps {
  request: AdminRequest;
  onApprove: (id: string) => void;
  approvingId: string | null;
}

function RequestRow({ request, onApprove, approvingId }: RequestRowProps) {
  const isBusy = approvingId === request.id;
  return (
    <li className="admin-modal__row admin-modal__row--request">
      <span className="admin-modal__cell admin-modal__cell--account" title={request.account}>{request.account}</span>
      <span className="admin-modal__cell admin-modal__cell--type">{request.requestType}</span>
      <span className="admin-modal__cell admin-modal__cell--remark" title={request.remark || "无备注"}>
        {request.remark || <em className="admin-modal__empty-remark">无备注</em>}
      </span>
      <span className="admin-modal__cell admin-modal__cell--date">{request.createdAt}</span>
      <button
        type="button"
        className={`admin-modal__approve-btn${isBusy ? " is-loading" : ""}`}
        disabled={approvingId !== null}
        onClick={() => onApprove(request.id)}
        aria-busy={isBusy}
      >
        {isBusy ? "处理中…" : "同意"}
      </button>
    </li>
  );
}

interface HistoryRowProps {
  record: AdminHistory;
  onDelete: (id: string) => void;
}

function HistoryRow({ record, onDelete }: HistoryRowProps) {
  return (
    <li className="admin-modal__row admin-modal__row--history">
      <span className="admin-modal__cell admin-modal__cell--account" title={record.account}>{record.account}</span>
      <span className="admin-modal__cell admin-modal__cell--type">{record.requestType}</span>
      <span className="admin-modal__cell admin-modal__cell--remark" title={record.remark || "无备注"}>
        {record.remark || <em className="admin-modal__empty-remark">无备注</em>}
      </span>
      <span className="admin-modal__cell admin-modal__cell--date">{record.approvedAt}</span>
      <span className="admin-modal__approved-tag">已同意</span>
      <button
        type="button"
        className="admin-modal__delete-btn"
        aria-label="删除此条记录"
        onClick={() => onDelete(record.id)}
      >
        ×
      </button>
    </li>
  );
}

export function AdminModal({ onClose, onPendingCountChange }: AdminModalProps) {
  const { username, setIsSelfCenterNode } = useAppRuntime();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [pendingUsers, setPendingUsers] = useState<AdminPendingUser[] | null>(null);
  const [requests, setRequests] = useState<AdminRequest[] | null>(null);
  const [history, setHistory] = useState<AdminHistory[] | null>(null);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [pendingBusyKey, setPendingBusyKey] = useState<string | null>(null);

  const notifyPendingCount = useCallback(
    (reqs: AdminRequest[] | null, pending: AdminPendingUser[] | null) => {
      onPendingCountChange?.((reqs?.length ?? 0) + (pending?.length ?? 0));
    },
    [onPendingCountChange],
  );

  useEffect(() => {
    void adminListUsers().then(setUsers);
    void adminListPendingUsers().then(setPendingUsers);
    void adminListRequests().then(setRequests);
    void adminListHistory().then(setHistory);
  }, []);

  // 注册申请数量变化时同步顶部“待处理”角标（与节点申请合计）
  useEffect(() => {
    if (pendingUsers === null && requests === null) return;
    notifyPendingCount(requests, pendingUsers);
  }, [notifyPendingCount, pendingUsers, requests]);

  // 通过 / 拒绝注册申请
  const handleDecideUser = useCallback(async (userId: number, approved: boolean) => {
    setPendingBusyKey(`u${userId}:${approved ? 1 : 0}`);
    try {
      const result = await adminApproveUser(userId, approved);
      if (result.ok) {
        const [updatedPending, updatedUsers] = await Promise.all([
          adminListPendingUsers(),
          adminListUsers(),
        ]);
        setPendingUsers(updatedPending);
        setUsers(updatedUsers);
      }
    } finally {
      setPendingBusyKey(null);
    }
  }, []);

  const handleDeleteHistory = useCallback((id: string) => {
    setHistory((prev) => prev ? prev.filter((h) => h.id !== id) : prev);
  }, []);

  const handleApprove = useCallback(async (id: string) => {
    // 先找到该请求，以便批准后判断是否需要更新当前用户状态
    const targetReq = requests?.find((r) => r.id === id);
    setApprovingId(id);
    try {
      const result = await adminApproveRequest(id);
      if (result.ok) {
        const [updatedReqs, updatedHistory] = await Promise.all([
          adminListRequests(),
          adminListHistory(),
        ]);
        setRequests(updatedReqs);
        setHistory(updatedHistory);
        notifyPendingCount(updatedReqs, pendingUsers);

        // 如果批准的是当前用户的中心节点申请，即时更新状态
        if (targetReq?.account === username) {
          if (targetReq.requestType === "申请成为中心节点") {
            setIsSelfCenterNode(true);
          } else if (targetReq.requestType === "申请还原为普通节点") {
            setIsSelfCenterNode(false);
          }
        }
      }
    } finally {
      setApprovingId(null);
    }
  }, [notifyPendingCount, pendingUsers, requests, username, setIsSelfCenterNode]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <section
      className="global-top-nav__profile-modal global-top-nav__profile-modal--long admin-modal"
      role="dialog"
      aria-modal="true"
      aria-label="管理员操作面板"
    >
      <div className="global-top-nav__profile-content global-top-nav__profile-content--long">
        <header className="global-top-nav__profile-modal-title-wrap">
          <h2 className="global-top-nav__profile-modal-title">管理员面板</h2>
        </header>

        {/* ── Section 1: User info ── */}
        <section className="global-top-nav__section admin-modal__section">
          <h3 className="global-top-nav__panel-title admin-modal__section-title">用户信息</h3>
          <div className="admin-modal__list-header admin-modal__list-header--user">
            <span>账号</span>
            <span>节点名称</span>
            <span>文献量</span>
            <span>类型</span>
          </div>
          <div className="admin-modal__scroll-area">
            {users === null ? (
              <SectionLoading />
            ) : users.length === 0 ? (
              <p className="admin-modal__list-empty">暂无用户</p>
            ) : (
              <ul className="admin-modal__list">
                {users.map((u) => (
                  <UserRow key={u.account} user={u} />
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* ── Section 1.5: Pending registrations ── */}
        <section className="global-top-nav__section admin-modal__section">
          <h3 className="global-top-nav__panel-title admin-modal__section-title">
            注册申请
            {pendingUsers !== null && pendingUsers.length > 0 && (
              <span className="admin-modal__pending-badge">{pendingUsers.length}</span>
            )}
          </h3>
          <div className="admin-modal__list-header admin-modal__list-header--pending">
            <span>账号</span>
            <span>邮箱</span>
            <span>申请日期</span>
            <span>操作</span>
          </div>
          <div className="admin-modal__scroll-area admin-modal__scroll-area--pending">
            {pendingUsers === null ? (
              <SectionLoading />
            ) : pendingUsers.length === 0 ? (
              <p className="admin-modal__list-empty">暂无待审核的注册申请</p>
            ) : (
              <ul className="admin-modal__list">
                {pendingUsers.map((u) => (
                  <PendingUserRow
                    key={u.id}
                    user={u}
                    onDecide={(id, approved) => void handleDecideUser(id, approved)}
                    busyKey={pendingBusyKey}
                  />
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* ── Section 2: Pending requests ── */}
        <section className="global-top-nav__section admin-modal__section">
          <h3 className="global-top-nav__panel-title admin-modal__section-title">
            用户申请
            {requests !== null && requests.length > 0 && (
              <span className="admin-modal__pending-badge">{requests.length}</span>
            )}
          </h3>
          <div className="admin-modal__list-header admin-modal__list-header--request">
            <span>账号</span>
            <span>申请类型</span>
            <span>备注</span>
            <span>日期</span>
            <span>操作</span>
          </div>
          <div className="admin-modal__scroll-area">
            {requests === null ? (
              <SectionLoading />
            ) : requests.length === 0 ? (
              <p className="admin-modal__list-empty">暂无待处理申请</p>
            ) : (
              <ul className="admin-modal__list">
                {requests.map((r) => (
                  <RequestRow
                    key={r.id}
                    request={r}
                    onApprove={(id) => void handleApprove(id)}
                    approvingId={approvingId}
                  />
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* ── Section 3: History ── */}
        <section className="global-top-nav__section admin-modal__section">
          <h3 className="global-top-nav__panel-title admin-modal__section-title">历史记录</h3>
          <div className="admin-modal__list-header admin-modal__list-header--history">
            <span>账号</span>
            <span>申请类型</span>
            <span>备注</span>
            <span>处理日期</span>
            <span>状态</span>
          </div>
          <div className="admin-modal__scroll-area">
            {history === null ? (
              <SectionLoading />
            ) : history.length === 0 ? (
              <p className="admin-modal__list-empty">暂无历史记录</p>
            ) : (
              <ul className="admin-modal__list">
                {history.map((h) => (
                  <HistoryRow key={h.id} record={h} onDelete={handleDeleteHistory} />
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
