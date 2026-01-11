import { useTheme } from "next-themes";
import { memo } from "react";
import { useTranslation } from "react-i18next";
import TradingViewTickerTape from "@/components/tradingview/tradingview-ticker-tape";

const INDEX_SYMBOLS = [
  "FOREXCOM:SPXUSD",
  "NASDAQ:IXIC",
  "NASDAQ:NDX",
  "INDEX:HSI",
  "SSE:000001",
  "BINANCE:BTCUSDT",
  "BINANCE:ETHUSDT",
];

function Prediction() {
  const { t, i18n } = useTranslation();
  const { resolvedTheme } = useTheme();

  return (
    <div className="flex h-full min-w-[800px] flex-col gap-6 p-6">
      <TradingViewTickerTape
        symbols={INDEX_SYMBOLS}
        theme={resolvedTheme === "dark" ? "dark" : "light"}
        locale={i18n.language}
      />

      <div className="flex flex-1 flex-col items-center justify-center gap-4">
        <div className="text-center">
          <h2 className="mb-2 font-semibold text-2xl text-foreground">
            {t("prediction.welcome")}
          </h2>
          <p className="text-muted-foreground">
            {t("prediction.selectStock")}
          </p>
        </div>
      </div>
    </div>
  );
}

export default memo(Prediction);
