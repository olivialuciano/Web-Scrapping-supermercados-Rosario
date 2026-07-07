from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS
import json
import time
import traceback

from scraper import ZONES, SCRAPERS, MARKET_NAMES


app = Flask(__name__)
CORS(app)


START_TIME = time.time()


def sse_event(event_name, data):
    """
    Formatea un evento SSE.
    El frontend lo escucha con:
    eventSource.addEventListener("progress", ...)
    """
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def build_final_response(product, zone, results, errors):
    products_with_price = [
        item for item in results
        if item.get("price") is not None
    ]

    products_without_price = [
        item for item in results
        if item.get("price") is None
    ]

    ranking = sorted(
        products_with_price,
        key=lambda item: item["price"]
    )

    final_results = ranking + products_without_price
    cheapest = ranking[0] if ranking else None

    return {
        "query": product,
        "zone": zone,
        "zone_name": ZONES[zone]["label"],
        "total_results": len(final_results),
        "cheapest": cheapest,
        "results": final_results,
        "errors": errors
    }


@app.get("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "SuperRos API funcionando",
        "endpoints": [
            "/api/health",
            "/api/warmup",
            "/api/zones",
            "/api/search",
            "/api/search-stream",
            "/api/debug/chrome"
        ]
    })


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "message": "API de supermercados funcionando"
    })


@app.get("/api/warmup")
def warmup():
    """
    Endpoint liviano para que el frontend despierte Render apenas carga la web.
    No abre Chrome ni ejecuta scraping: solo responde rápido y mantiene viva la API.
    """
    uptime_seconds = round(time.time() - START_TIME, 2)

    return jsonify({
        "status": "ok",
        "message": "API despierta",
        "uptime_seconds": uptime_seconds,
        "available_zones": list(ZONES.keys()),
        "available_markets": list(MARKET_NAMES.values())
    })


@app.get("/api/debug/chrome")
def debug_chrome():
    from scraper import start_market_browser, safe_kill_browser
    import os
    import subprocess
    import traceback

    info = {
        "chrome_bin": os.environ.get("CHROME_BIN"),
        "home": os.environ.get("HOME")
    }

    try:
        chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")

        chrome_version = subprocess.check_output(
            [chrome_bin, "--version"],
            text=True,
            stderr=subprocess.STDOUT
        ).strip()

        info["chrome_version"] = chrome_version

        standalone_test = subprocess.check_output(
            [
                chrome_bin,
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--dump-dom",
                "https://example.com"
            ],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=40
        )

        info["standalone_chrome_ok"] = "Example Domain" in standalone_test

        driver = start_market_browser("https://example.com")
        title = driver.title

        safe_kill_browser()

        return jsonify({
            "status": "ok",
            "title": title,
            **info
        })

    except Exception as error:
        safe_kill_browser()

        return jsonify({
            "status": "error",
            "message": str(error),
            "trace": traceback.format_exc(),
            **info
        }), 500


@app.get("/api/zones")
def get_zones():
    return jsonify({
        "zones": ZONES
    })


@app.get("/api/search-stream")
def search_stream():
    product = request.args.get("product", "").strip()
    zone = request.args.get("zone", "Q").strip().upper()
    limit = request.args.get("limit", "3")

    try:
        limit = int(limit)
    except ValueError:
        limit = 3

    if not product:
        return jsonify({
            "error": "Tenés que ingresar un producto para buscar."
        }), 400

    if zone not in ZONES:
        return jsonify({
            "error": "Zona inválida.",
            "available_zones": ZONES
        }), 400

    @stream_with_context
    def generate():
        all_results = []
        errors = []

        markets = ZONES[zone]["markets"]
        total_markets = len(markets)

        yield sse_event("progress", {
            "percentage": 0,
            "message": "Preparando búsqueda...",
            "current_market": None,
            "finished_markets": 0,
            "total_markets": total_markets
        })

        for index, market_key in enumerate(markets):
            scraper = SCRAPERS.get(market_key)
            market_name = MARKET_NAMES.get(market_key, market_key)

            start_percentage = round((index / total_markets) * 100)

            yield sse_event("progress", {
                "percentage": start_percentage,
                "message": f"Buscando en {market_name}...",
                "current_market": market_name,
                "finished_markets": index,
                "total_markets": total_markets
            })

            if scraper is None:
                errors.append({
                    "supermarket": market_name,
                    "message": "No hay scraper configurado para este supermercado."
                })

                done_percentage = round(((index + 1) / total_markets) * 100)

                yield sse_event("progress", {
                    "percentage": done_percentage,
                    "message": f"{market_name} no tiene scraper configurado.",
                    "current_market": market_name,
                    "finished_markets": index + 1,
                    "total_markets": total_markets
                })

                continue

            try:
                market_results = scraper(product, limit=limit)
                all_results.extend(market_results)

                if len(market_results) == 0:
                    errors.append({
                        "supermarket": market_name,
                        "message": "No se encontraron resultados."
                    })

            except Exception as error:
                errors.append({
                    "supermarket": market_name,
                    "message": str(error),
                    "trace": traceback.format_exc()
                })

            done_percentage = round(((index + 1) / total_markets) * 100)

            yield sse_event("progress", {
                "percentage": done_percentage,
                "message": f"Terminamos de buscar en {market_name}.",
                "current_market": market_name,
                "finished_markets": index + 1,
                "total_markets": total_markets
            })

        final_response = build_final_response(
            product=product,
            zone=zone,
            results=all_results,
            errors=errors
        )

        yield sse_event("complete", {
            "percentage": 100,
            "message": "Búsqueda finalizada.",
            "data": final_response
        })

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/search")
def search():
    """
    Endpoint viejo/simple.
    Lo podés dejar por si querés una búsqueda sin progreso.
    """
    product = request.args.get("product", "").strip()
    zone = request.args.get("zone", "Q").strip().upper()
    limit = request.args.get("limit", "3")

    try:
        limit = int(limit)
    except ValueError:
        limit = 3

    if not product:
        return jsonify({
            "error": "Tenés que ingresar un producto para buscar."
        }), 400

    if zone not in ZONES:
        return jsonify({
            "error": "Zona inválida.",
            "available_zones": ZONES
        }), 400

    all_results = []
    errors = []

    markets = ZONES[zone]["markets"]

    for market_key in markets:
        scraper = SCRAPERS.get(market_key)
        market_name = MARKET_NAMES.get(market_key, market_key)

        try:
            market_results = scraper(product, limit=limit)
            all_results.extend(market_results)
        except Exception as error:
            errors.append({
                "supermarket": market_name,
                "message": str(error),
                "trace": traceback.format_exc()
            })

    return jsonify(
        build_final_response(
            product=product,
            zone=zone,
            results=all_results,
            errors=errors
        )
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
