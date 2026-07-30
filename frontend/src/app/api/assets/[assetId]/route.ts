import { NextRequest, NextResponse } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: { assetId: string } }
) {
  const assetId = params.assetId;

  // 代理请求到后端
  const backendUrl = `${process.env.BACKEND_URL}/api/assets/${assetId}/download-url`;

  try {
    const response = await fetch(backendUrl, {
      headers: {
        // 透传前端的 cookie 或 token
        Cookie: request.headers.get("cookie") || "",
      },
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("BFF 代理获取视频播放地址失败:", error);
    return NextResponse.json(
      { error: "无法获取视频播放地址" },
      { status: 500 }
    );
  }
}