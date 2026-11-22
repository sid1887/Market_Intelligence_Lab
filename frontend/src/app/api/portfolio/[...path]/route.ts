import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function getBackendBase(): string {
  const raw =
    process.env.BACKEND_API_URL ||
    process.env.RENDER_BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000/api/v1";
  return raw.endsWith("/api/v1") ? raw : `${raw.replace(/\/$/, "")}/api/v1`;
}

async function proxyRequest(request: NextRequest, { params }: { params: { path?: string[] } }) {
  try {
    const subpath = params.path ? params.path.join("/") : "";
    const backendBase = getBackendBase();
    const urlObj = new URL(request.url);
    const targetUrl = `${backendBase}/portfolio/${subpath}${urlObj.search}`;

    const headers: Record<string, string> = {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "true",
    };

    // Inject server-side secret API key (kept strictly out of the public client browser bundle)
    const serverApiKey = process.env.MIL_API_KEY || process.env.MIL_INTERNAL_SYNC_SECRET;
    if (serverApiKey) {
      headers["X-API-Key"] = serverApiKey;
    } else {
      // Forward client header if present
      const clientKey = request.headers.get("x-api-key");
      if (clientKey) {
        headers["X-API-Key"] = clientKey;
      }
    }

    const method = request.method;
    let body: string | undefined = undefined;
    if (method !== "GET" && method !== "HEAD") {
      body = await request.text();
    }

    const backendRes = await fetch(targetUrl, {
      method,
      headers,
      body,
      cache: "no-store",
    });

    const responseText = await backendRes.text();
    return new NextResponse(responseText, {
      status: backendRes.status,
      headers: {
        "Content-Type": backendRes.headers.get("content-type") || "application/json",
      },
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      { error: "Internal Portfolio Proxy Error", details: message },
      { status: 502 }
    );
  }
}

export async function GET(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}

export async function POST(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}

export async function PUT(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}

export async function DELETE(request: NextRequest, context: { params: { path?: string[] } }) {
  return proxyRequest(request, context);
}
