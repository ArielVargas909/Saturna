import { describe, expect, it } from "vitest";
import { STATE_LABEL, bs, dt } from "./format";

describe("format", () => {
  it("formatea bolivianos con dos decimales", () => {
    expect(bs(5)).toMatch(/^Bs 5[.,]00$/);
    expect(bs("12.5")).toMatch(/12[.,]50$/);
    expect(bs(null)).toMatch(/^Bs 0[.,]00$/);
  });
  it("maneja fechas vacías", () => {
    expect(dt(null)).toBe("—");
  });
  it("tiene etiqueta para todos los estados", () => {
    for (const s of [
      "REGISTRADO",
      "NOTIFICADO",
      "LISTO_PARA_RETIRO",
      "ENTREGADO",
      "ESTANCADO",
      "DEVUELTO",
      "VENCIDO",
    ])
      expect(STATE_LABEL[s]).toBeTruthy();
  });
});
