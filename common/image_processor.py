import logging
import io
import json
from typing import Dict, List, Optional, Any, Tuple
from fastapi import HTTPException
from PIL import Image
import boto3
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)


class ImageProcessor:
    def __init__(self, region_name: str = "ap-southeast-2"):
        self.textract_client = boto3.client("textract", region_name=region_name)

    async def process_image(
        self, image_data: bytes, source: str = "upload"
    ) -> Dict[str, Any]:
        """
        Process an image using Amazon Textract to extract table data and booth name.

        Args:
            image_data: Raw image data in bytes
            source: Source of the image ("upload" or "sms")

        Returns:
            Dictionary containing extracted data including tables and booth name
        """
        try:
            logger.info(f"Processing image from {source}")

            # Validate and preprocess image
            try:
                image = Image.open(io.BytesIO(image_data))
                # Convert to RGB if needed
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                # Convert back to bytes in PNG format
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format="PNG")
                image_data = img_byte_arr.getvalue()
            except Exception as e:
                logger.error(f"Error preprocessing image: {e}")
                raise HTTPException(status_code=400, detail="Invalid image format")

            # Send image to Textract with TABLES + QUERIES
            logger.info("Sending image to Amazon Textract...")
            response = self.textract_client.analyze_document(
                Document={"Bytes": image_data},
                FeatureTypes=["TABLES", "QUERIES"],
                QueriesConfig={
                    "Queries": [
                        {"Text": "What is the BOOTH NAME?", "Alias": "BoothName"}
                    ]
                },
            )
            logger.info("Received response from Textract.")

            blocks_map = {block["Id"]: block for block in response["Blocks"]}
            tables = []
            booth_name = None

            for block in response["Blocks"]:
                if block["BlockType"] == "TABLE":
                    tables.append(block)
                if block["BlockType"] == "QUERY_RESULT":
                    booth_name = block.get("Text", "").strip()

            logger.info(f"Found {len(tables)} tables.")
            logger.info(f"Extracted booth name: {booth_name}")

            # Pick the second table if available
            if len(tables) >= 2:
                target_table = tables[1]
            elif len(tables) == 1:
                target_table = tables[0]
            else:
                raise Exception("No tables found in document.")

            # Extract table cells
            extracted_rows = self._extract_table(target_table, blocks_map)
            logger.info(f"Extracted {len(extracted_rows)} cells from the target table.")

            return {
                "extracted_rows": extracted_rows,
                "booth_name": booth_name,
                "tables": tables,
                "source": source,
            }

        except Exception as e:
            logger.error(f"Error processing image: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def _extract_table(self, table_block: Dict, blocks_map: Dict) -> List[Dict]:
        """
        Extract data from a table block.

        Args:
            table_block: The table block from Textract
            blocks_map: Map of all blocks from Textract

        Returns:
            List of extracted cells with row and column indices
        """
        table_data = []
        for relationship in table_block.get("Relationships", []):
            if relationship["Type"] == "CHILD":
                for child_id in relationship["Ids"]:
                    child = blocks_map[child_id]
                    if child["BlockType"] == "CELL":
                        text = ""
                        for rel in child.get("Relationships", []):
                            for grandchild_id in rel["Ids"]:
                                word = blocks_map[grandchild_id]
                                if word["BlockType"] == "WORD":
                                    text += word["Text"] + " "
                        table_data.append(
                            {
                                "RowIndex": child["RowIndex"],
                                "ColumnIndex": child["ColumnIndex"],
                                "Text": text.strip(),
                            }
                        )
        return table_data

    async def process_sms_image(self, media_url: str) -> Dict[str, Any]:
        """
        Process an image from an SMS media URL.

        Args:
            media_url: URL of the image to process

        Returns:
            Dictionary containing extracted data
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(media_url)
                image_data = response.content

            return await self.process_image(image_data, source="sms")

        except Exception as e:
            logger.error(f"Error processing SMS image: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
