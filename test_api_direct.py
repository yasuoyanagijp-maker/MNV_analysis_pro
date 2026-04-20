
import httpx
import asyncio
import base64
from pathlib import Path

async def test_api():
    url = "http://127.0.0.1:8000/analyze/mnv"
    
    # Use the same image as the successful direct test
    image_path = "/tmp/mnv_samples/Main Report1.png"
    
    payload = {
        "image_path": image_path,
        "scale_mm": 6.0,
        "intelligent_roi": True,
        "save_stages": True
    }
    
    print(f"Sending request to {url}...")
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.post(url, json=payload)
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print("Success!")
                print(f"Metrics: {data.get('results', {}).keys()}")
            else:
                print("Error Response:")
                print(response.json())
        except Exception as e:
            print(f"Connection failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_api())
