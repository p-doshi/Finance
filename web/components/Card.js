export default function Card({ children, style, className = "" }) {
  return (
    <div className={`card ${className}`.trim()} style={style}>
      {children}
    </div>
  );
}
