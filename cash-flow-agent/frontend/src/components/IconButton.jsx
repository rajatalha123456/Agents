export default function IconButton({ icon: Icon, onClick, tone, title, type = "button" }) {
  return (
    <button
      type={type}
      onClick={onClick}
      title={title}
      className="btn-ghost !px-1.5 !py-1.5"
      style={tone === "danger" ? { color: "var(--danger-600)" } : undefined}
    >
      <Icon size={14} />
    </button>
  );
}
