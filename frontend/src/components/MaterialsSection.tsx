import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { formatMoney } from "../lib/format";

interface Materials {
  materials: { item_id: number; name: string; unit: string; quantity: string; value: string | null }[];
  total_value: string;
  currency: string;
}

/** Stock issued to this project from the inventory. Shown only when there is some. */
export function MaterialsSection({ projectId, refreshKey }: { projectId: number; refreshKey: number }) {
  const [data, setData] = useState<Materials | null>(null);

  useEffect(() => {
    api<Materials>(`/projects/${projectId}/materials`)
      .then(setData)
      .catch(() => setData(null));
  }, [projectId, refreshKey]);

  if (!data || data.materials.length === 0) return null;

  return (
    <section className="projects-section" aria-labelledby="materials-heading">
      <div className="section-head">
        <h2 id="materials-heading">Materials used</h2>
        <Link to="/app/inventory">Inventory</Link>
      </div>
      <table className="report__table">
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col" className="num">
              Issued
            </th>
            <th scope="col" className="num">
              Value
            </th>
          </tr>
        </thead>
        <tbody>
          {data.materials.map((m) => (
            <tr key={m.item_id}>
              <td>{m.name}</td>
              <td className="num">
                {Number(m.quantity).toLocaleString("en-US", { maximumFractionDigits: 2 })} {m.unit}
              </td>
              <td className="num">{m.value ? formatMoney(m.value, data.currency) : "No unit cost"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted report__note">
        Total {formatMoney(data.total_value, data.currency)} at current unit costs. Stock issued from inventory isn't
        counted in the project's spending; record a purchase as an expense if it should be.
      </p>
    </section>
  );
}
