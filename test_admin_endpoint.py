import requests
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

def test_admin_endpoint():
    """Test the admin endpoint for loading reference data"""
    try:
        logger.info("Testing admin endpoint for loading reference data")
        response = requests.get('http://localhost:8000/admin/load-reference-data')
        logger.info(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Response: {json.dumps(result, indent=2)}")
            
            if result.get('status') == 'success':
                candidates_loaded = result.get('details', {}).get('candidates_loaded', False)
                booth_results_loaded = result.get('details', {}).get('booth_results_loaded', False)
                
                logger.info(f"Candidates loaded: {candidates_loaded}")
                logger.info(f"Booth results loaded: {booth_results_loaded}")
                
                if candidates_loaded and booth_results_loaded:
                    logger.info("✅ Admin endpoint test passed - all reference data loaded successfully")
                    return True
                else:
                    logger.error("❌ Admin endpoint test failed - not all reference data was loaded")
                    return False
            else:
                logger.error(f"❌ Admin endpoint test failed - status: {result.get('status')}")
                return False
        else:
            logger.error(f"❌ Admin endpoint test failed - status code: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Error testing admin endpoint: {e}")
        return False

if __name__ == "__main__":
    test_admin_endpoint()
