#!/usr/bin/env python3
# =============================================================================
# Orion Client - NGSI-LD Entity Writer for Predictions
# =============================================================================
# Handles creation and updates of Prediction entities in Orion-LD.
# This module is designed to be easily extractable to a separate service.

import logging
import os
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

# NGSI-LD core context (ETSI standard) — used as fallback when CONTEXT_URL is not configured
NGSI_LD_CORE_CONTEXT = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"

# Configuration
ORION_URL = os.getenv('ORION_URL', 'http://orion-ld-service:1026')
CONTEXT_URL = os.getenv('CONTEXT_URL', '')


def _normalize_tenant(tenant_id: str) -> str:
    """Normalize tenant ID for consistency across platform services."""
    n = tenant_id.lower().strip().replace('-', '_').replace(' ', '_')
    n = re.sub(r'[^a-z0-9_]', '', n)
    return n.strip('_') or tenant_id


def inject_fiware_headers(headers: Dict[str, str], tenant_id: str, context_url: Optional[str] = None) -> Dict[str, str]:
    """Inject NGSI-LD + FIWARE tenant headers for Orion-LD requests.

    Sends BOTH NGSILD-Tenant (ETSI standard) AND Fiware-Service (legacy)
    with normalized tenant ID.
    """
    n = _normalize_tenant(tenant_id)
    headers['NGSILD-Tenant'] = n
    headers['Fiware-Service'] = n
    headers['Fiware-ServicePath'] = '/'
    headers['Content-Type'] = 'application/ld+json'
    headers['Accept'] = 'application/ld+json'

    url = context_url or CONTEXT_URL
    if url:
        headers['Link'] = f'<{url}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'

    return headers


async def create_prediction_entity(
    entity_id: str,
    tenant_id: str,
    ref_entity_id: str,
    predicted_attribute: str,
    predictions: List[Dict[str, Any]],
    model: str = "linear_regression",
    confidence: float = 0.85,
    headers: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """
    Create a Prediction entity in Orion-LD following NGSI-LD standard.
    
    Args:
        entity_id: Prediction entity ID (e.g., "urn:ngsi-ld:Prediction:temperature-2024-01-15")
        tenant_id: Tenant ID for multi-tenancy
        ref_entity_id: ID of the entity being predicted (e.g., sensor, parcel)
        predicted_attribute: Name of the attribute being predicted (e.g., "temperature")
        predictions: List of prediction points [{"timestamp": "2024-01-15T10:00:00Z", "value": 22.5}, ...]
        model: Model name used for prediction
        confidence: Confidence score (0.0 to 1.0)
        headers: Optional headers dict
        
    Returns:
        Entity ID if successful, None otherwise
    """
    try:
        if headers is None:
            headers = {}
        
        headers = inject_fiware_headers(headers, tenant_id)
        
        # Build Prediction entity following NGSI-LD standard
        entity = {
            '@context': [CONTEXT_URL or NGSI_LD_CORE_CONTEXT],
            'id': entity_id,
            'type': 'Prediction',
            'refEntity': {
                'type': 'Relationship',
                'object': ref_entity_id
            },
            'predictedAttribute': {
                'type': 'Property',
                'value': predicted_attribute
            },
            'predictions': {
                'type': 'Property',
                'value': predictions
            },
            'model': {
                'type': 'Property',
                'value': model
            },
            'confidence': {
                'type': 'Property',
                'value': float(confidence),
                'unitCode': 'C62'  # Dimensionless unit (0-1 scale)
            },
            'createdAt': {
                'type': 'Property',
                'value': {
                    '@type': 'DateTime',
                    '@value': datetime.utcnow().isoformat() + 'Z'
                }
            },
            'updatedAt': {
                'type': 'Property',
                'value': {
                    '@type': 'DateTime',
                    '@value': datetime.utcnow().isoformat() + 'Z'
                }
            }
        }
        
        # Try to create entity
        orion_endpoint = f"{ORION_URL}/ngsi-ld/v1/entities"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(orion_endpoint, json=entity, headers=headers)
        
        if response.status_code in [201, 204]:
            logger.info(f"Created Prediction entity {entity_id} for {ref_entity_id}")
            return entity_id
        elif response.status_code == 409:
            # Entity already exists, update it
            logger.info(f"Prediction entity {entity_id} already exists, updating...")
            return await update_prediction_entity(entity_id, tenant_id, predictions, confidence, headers)
        else:
            logger.error(f"Failed to create Prediction entity: {response.status_code} - {response.text[:200]}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating Prediction entity: {e}", exc_info=True)
        return None


async def update_prediction_entity(
    entity_id: str,
    tenant_id: str,
    predictions: List[Dict[str, Any]],
    confidence: float,
    headers: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """
    Update an existing Prediction entity in Orion-LD.
    
    Args:
        entity_id: Prediction entity ID
        tenant_id: Tenant ID
        predictions: Updated predictions list
        confidence: Updated confidence score
        headers: Optional headers dict
        
    Returns:
        Entity ID if successful, None otherwise
    """
    try:
        if headers is None:
            headers = {}
        
        headers = inject_fiware_headers(headers, tenant_id)
        
        # Build update payload
        update_payload = {
            'predictions': {
                'type': 'Property',
                'value': predictions
            },
            'confidence': {
                'type': 'Property',
                'value': float(confidence),
                'unitCode': 'C62'
            },
            'updatedAt': {
                'type': 'Property',
                'value': {
                    '@type': 'DateTime',
                    '@value': datetime.utcnow().isoformat() + 'Z'
                }
            }
        }
        
        # Update entity attributes
        orion_endpoint = f"{ORION_URL}/ngsi-ld/v1/entities/{entity_id}/attrs"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(orion_endpoint, json=update_payload, headers=headers)
        
        if response.status_code in [200, 204]:
            logger.info(f"Updated Prediction entity {entity_id}")
            return entity_id
        else:
            logger.error(f"Failed to update Prediction entity: {response.status_code} - {response.text[:200]}")
            return None
            
    except Exception as e:
        logger.error(f"Error updating Prediction entity: {e}", exc_info=True)
        return None

