/**
 * frontend/src/lib/friction.ts
 * Canonical Indian Equity Cash Delivery & Angel One Fee Engine.
 * Reconciles roundtrip friction: ₹23.60 DP fee + STT + stamp duty + exchange/SEBI + GST.
 */

export interface TicketFrictionResult {
  shares: number;
  invested: number;
  totalFriction: number;
  feeDragPct: number;
  grossReward: number;
  grossRisk: number;
  netReward: number;
  netRisk: number;
  netRR: number;
  status: "EXECUTABLE" | "NO_TRADE (DP DRAG)" | "NO_TRADE (TICKET < PRICE)";
  isExecutable: boolean;
}

export const TICKET_SIZES = [2500, 5000, 10000, 25000] as const;
export type TicketSize = (typeof TICKET_SIZES)[number];

export function computeTicketFriction(
  close: number | null | undefined,
  ticketSize: number = 5000,
  targetPct: number = 0.12,  // 12% target
  stopPct: number = 0.06     // 6% stop
): TicketFrictionResult {
  if (!close || close <= 0) {
    return {
      shares: 0,
      invested: 0,
      totalFriction: 0,
      feeDragPct: 0,
      grossReward: 0,
      grossRisk: 0,
      netReward: 0,
      netRisk: 0,
      netRR: 0,
      status: "NO_TRADE (DP DRAG)",
      isExecutable: false,
    };
  }

  const shares = Math.floor(ticketSize / close);
  if (shares < 1) {
    return {
      shares: 0,
      invested: 0,
      totalFriction: 0,
      feeDragPct: 99.9,
      grossReward: 0,
      grossRisk: 0,
      netReward: 0,
      netRisk: 0,
      netRR: 0,
      status: "NO_TRADE (TICKET < PRICE)",
      isExecutable: false,
    };
  }

  const buyTurnover = shares * close;
  const winPrice = close * (1 + targetPct);
  const lossPrice = close * (1 - stopPct);
  const winTurnover = shares * winPrice;
  const lossTurnover = shares * lossPrice;

  // Angel One delivery zero brokerage profile
  const buyStt = Math.round(0.001 * buyTurnover);
  const sellWinStt = Math.round(0.001 * winTurnover);
  const sellLossStt = Math.round(0.001 * lossTurnover);

  const buyStamp = Math.round(0.00015 * buyTurnover);
  const dpFee = 23.60; // ₹20 CDSL base + 18% GST

  const buyTxn = 0.000030699 * buyTurnover;
  const sellWinTxn = 0.000030699 * winTurnover;
  const sellLossTxn = 0.000030699 * lossTurnover;

  const buySebi = 0.000001 * buyTurnover;
  const sellWinSebi = 0.000001 * winTurnover;
  const sellLossSebi = 0.000001 * lossTurnover;

  const buyGst = 0.18 * (buyTxn + buySebi);
  const sellWinGst = 0.18 * (sellWinTxn + sellWinSebi);
  const sellLossGst = 0.18 * (sellLossTxn + sellLossSebi);

  const totalWinFriction = (
    buyStt + sellWinStt +
    buyStamp + dpFee +
    buyTxn + sellWinTxn +
    buySebi + sellWinSebi +
    buyGst + sellWinGst
  );

  const totalLossFriction = (
    buyStt + sellLossStt +
    buyStamp + dpFee +
    buyTxn + sellLossTxn +
    buySebi + sellLossSebi +
    buyGst + sellLossGst
  );

  const feeDragPct = Number(((totalWinFriction / buyTurnover) * 100).toFixed(2));
  const grossReward = shares * (winPrice - close);
  const grossRisk = shares * (close - lossPrice);

  const netReward = grossReward - totalWinFriction;
  const netRisk = grossRisk + totalLossFriction;
  const netRR = Number((netReward / Math.max(netRisk, 0.01)).toFixed(2));

  // Executable criteria: roundtrip fee drag <= 1.25% and post-cost net R:R >= 1.6
  const isExecutable = feeDragPct <= 1.25 && netRR >= 1.6;
  const status: "EXECUTABLE" | "NO_TRADE (DP DRAG)" = isExecutable ? "EXECUTABLE" : "NO_TRADE (DP DRAG)";

  return {
    shares,
    invested: Number(buyTurnover.toFixed(2)),
    totalFriction: Number(totalWinFriction.toFixed(2)),
    feeDragPct,
    grossReward: Number(grossReward.toFixed(2)),
    grossRisk: Number(grossRisk.toFixed(2)),
    netReward: Number(netReward.toFixed(2)),
    netRisk: Number(netRisk.toFixed(2)),
    netRR,
    status,
    isExecutable,
  };
}
