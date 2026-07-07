import { useMemo, useRef, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL;

const zones = [
  { value: "Q", label: "Cualquier zona" },
  { value: "C", label: "Centro" },
  { value: "S", label: "Sur" },
  { value: "O", label: "Oeste" },
  { value: "F", label: "Fisherton" },
  { value: "N", label: "Norte" },
];

function formatPrice(price) {
  if (price === null || price === undefined) {
    return "Precio no disponible";
  }

  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "ARS",
    maximumFractionDigits: 2,
  }).format(price);
}

function ProductImage({ src, alt }) {
  const [hasError, setHasError] = useState(false);

  if (!src || hasError) {
    return <div className="product-image-placeholder">Sin imagen</div>;
  }

  return (
    <img
      src={src}
      alt={alt}
      className="product-image"
      loading="lazy"
      onError={() => setHasError(true)}
    />
  );
}

function App() {
  const [product, setProduct] = useState("");
  const [zone, setZone] = useState("Q");
  const [limit, setLimit] = useState(3);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");
  const [finishedMarkets, setFinishedMarkets] = useState(0);
  const [totalMarkets, setTotalMarkets] = useState(0);
  const progressIntervalRef = useRef(null);
  const progressValueRef = useRef(0);

  const cheapestId = useMemo(() => {
    if (!data?.cheapest) return null;

    return `${data.cheapest.supermarket}-${data.cheapest.product_name}-${data.cheapest.price}`;
  }, [data]);

  function stopProgressAnimation() {
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current);
      progressIntervalRef.current = null;
    }
  }

  function setProgressSmoothly(targetProgress, speed = 500) {
    stopProgressAnimation();

    const safeTarget = Math.min(Math.max(targetProgress, 0), 100);

    progressIntervalRef.current = setInterval(() => {
      const currentProgress = progressValueRef.current;

      if (currentProgress >= safeTarget) {
        stopProgressAnimation();
        return;
      }

      const nextProgress = currentProgress + 1;

      progressValueRef.current = nextProgress;
      setProgress(nextProgress);
    }, speed);
  }

  function setProgressImmediately(value) {
    stopProgressAnimation();

    const safeValue = Math.min(Math.max(value, 0), 100);

    progressValueRef.current = safeValue;
    setProgress(safeValue);
  }

  function handleSubmit(event) {
    event.preventDefault();

    const trimmedProduct = product.trim();

    if (!trimmedProduct) {
      return;
    }

    setLoading(true);
    setData(null);

    setProgressImmediately(0);
    setProgressMessage("Preparando búsqueda...");
    setFinishedMarkets(0);
    setTotalMarkets(0);

    const params = new URLSearchParams({
      product: trimmedProduct,
      zone,
      limit: String(limit),
    });

    const eventSource = new EventSource(
      `${API_URL}/api/search-stream?${params.toString()}`,
    );

    eventSource.addEventListener("progress", (event) => {
      const payload = JSON.parse(event.data);

      const backendProgress = payload.percentage ?? 0;
      const finished = payload.finished_markets ?? 0;
      const total = payload.total_markets ?? 0;

      setProgressMessage(payload.message ?? "");
      setFinishedMarkets(finished);
      setTotalMarkets(total);

      if (total > 0 && payload.current_market) {
        const currentMarketTarget = Math.round(((finished + 1) / total) * 100);
        const animatedTarget = Math.max(
          currentMarketTarget - 1,
          backendProgress,
        );

        setProgressSmoothly(animatedTarget, 500);
      } else {
        setProgressSmoothly(backendProgress, 500);
      }

      if (payload.message?.startsWith("Terminamos")) {
        setProgressSmoothly(backendProgress, 280);
      }
    });

    eventSource.addEventListener("complete", (event) => {
      const payload = JSON.parse(event.data);

      setProgressSmoothly(100, 25);
      setProgressMessage(payload.message ?? "Búsqueda finalizada.");
      setData(payload.data);

      setTimeout(() => {
        setLoading(false);
        eventSource.close();
        stopProgressAnimation();
        setProgressImmediately(100);
      }, 700);
    });

    eventSource.onerror = () => {
      setLoading(false);
      eventSource.close();
      stopProgressAnimation();
    };
  }

  return (
    <main className="page">
      <section className="results-section">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark">
              <span />
              <span />
            </div>
            <strong>SuperRos</strong>
          </div>
        </header>

        <section className="hero-layout">
          <section className="hero-main">
            <div className="review-pill">
              <p>comparador local en tiempo real</p>
            </div>

            <div className="headline-row">
              <h1>
                Compará precios de supermercados en Rosario
                <span className="title-bubbles">
                  <i />
                  <i />
                  <i />
                </span>
              </h1>
            </div>

            <p className="hero-description">
              Buscá un producto, elegí una zona y mirá un ranking visual de
              opciones ordenadas de más barato a más caro, con imagen, detalle
              del producto y nombre del supermercado.
            </p>
          </section>

          <aside className="hero-showcase" aria-label="Panel visual">
            <article className="showcase-card showcase-primary">
              <div className="showcase-top">
                <span className="showcase-label">live ranking</span>
                <span className="showcase-badge">Rosario</span>
              </div>

              <div className="showcase-art">
                <div className="blob blob-orange" />
                <div className="blob blob-yellow" />
                <div className="blob blob-outline" />
              </div>

              <div className="showcase-copy">
                <h3>Compará en segundos dónde conviene comprar</h3>
                <p>
                  Una forma más visual, simple y rápida de revisar precios sin
                  descargar archivos.
                </p>
              </div>
            </article>
          </aside>
        </section>
        <br />

        <section className="search-zone">
          <form className="search-card" onSubmit={handleSubmit}>
            <div className="field field-large">
              <label htmlFor="product">Producto</label>
              <input
                id="product"
                type="text"
                placeholder="Ej: rosamonte, playadito, canarias..."
                value={product}
                onChange={(event) => setProduct(event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="zone">Zona</label>
              <select
                id="zone"
                value={zone}
                onChange={(event) => setZone(event.target.value)}
              >
                {zones.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="limit">Resultados</label>
              <select
                id="limit"
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
              >
                <option value={1}>1 por súper</option>
                <option value={2}>2 por súper</option>
                <option value={3}>3 por súper</option>
                <option value={5}>5 por súper</option>
              </select>
            </div>

            <button className="search-button" type="submit" disabled={loading}>
              {loading ? "Buscando..." : "Buscar ahora"}
              <span>→</span>
            </button>
          </form>

          <br />

          <div className="hero-inline-info">
            <article className="inline-chip chip-yellow">
              Precio + imagen + detalle de producto
            </article>
            <article className="inline-chip">Ranking automático</article>
            <article className="inline-chip">Scraping en vivo</article>
          </div>

          <div className="hero-stats">
            <article>
              <span>01</span>
              <strong>Ranking inteligente</strong>
              <p>
                Los resultados se ordenan automáticamente desde el precio más
                bajo hasta el más alto.
              </p>
            </article>

            <article>
              <span>02</span>
              <strong>Comparación visual</strong>
              <p>
                Ves producto, supermercado, imagen y precio en una misma
                tarjeta.
              </p>
            </article>
          </div>
        </section>
      </section>

      {(loading || data) && (
        <section className="loading-card">
          <div className="loading-content">
            <div className="loading-header">
              <div>
                <p className="eyebrow">Scraping en progreso</p>
                <h2>{progressMessage || "Buscando precios..."}</h2>

                {totalMarkets > 0 && (
                  <p>
                    Supermercados revisados: {finishedMarkets} de {totalMarkets}
                  </p>
                )}
              </div>

              <div className="progress-percentage">{progress}%</div>
            </div>

            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </section>
      )}

      {data && !loading && (
        <section className="results-section">
          <div className="results-header">
            <div>
              <p className="eyebrow">Resultados</p>
              <h2>Ranking para “{data.query}”</h2>
            </div>

            {data.cheapest && (
              <div className="best-price-card">
                <span>Más barato</span>
                <strong>{formatPrice(data.cheapest.price)}</strong>
                <p>{data.cheapest.supermarket}</p>
              </div>
            )}
          </div>

          {data.results.length === 0 ? (
            <div className="empty-card">
              <h3>No encontramos productos.</h3>
              <p>
                Probá buscar con otra palabra. Por ejemplo, en vez de “leche de
                almendras”, buscá “leche”.
              </p>
            </div>
          ) : (
            <div className="ranking-list">
              {data.results.map((item, index) => {
                const id = `${item.supermarket}-${item.product_name}-${item.price}`;
                const isCheapest = id === cheapestId;

                return (
                  <article
                    className={`product-card ${isCheapest ? "is-cheapest" : ""}`}
                    key={`${id}-${index}`}
                  >
                    <div className="rank-number">#{index + 1}</div>

                    <div className="product-detail">
                      <div className="product-image-wrapper">
                        <ProductImage
                          src={item.image_url}
                          alt={item.product_name}
                        />
                      </div>

                      <div className="product-info">
                        <div className="product-title-row">
                          <h3>{item.product_name}</h3>

                          {isCheapest && (
                            <span className="cheapest-badge">Mejor precio</span>
                          )}
                        </div>

                        <p className="supermarket-name">{item.supermarket}</p>
                      </div>
                    </div>

                    <div className="price-box">
                      <span>Precio</span>
                      <strong>{formatPrice(item.price)}</strong>
                      {item.price_text && <small>{item.price_text}</small>}
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {data.errors.length > 0 && (
            <div className="errors-panel">
              <h3>Avisos del scraping</h3>

              <ul>
                {data.errors.map((error, index) => (
                  <li key={`${error.supermarket}-${index}`}>
                    <strong>{error.supermarket}:</strong> {error.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

export default App;
