def calculate_risk(
    rainfall,
    soil_moisture,
    slope,
    elevation,
    past_landslide
):
    score = 0

    # Rainfall risk
    if rainfall >= 200:
        score += 30
    elif rainfall >= 100:
        score += 20
    elif rainfall >= 50:
        score += 10

    # Soil moisture risk
    if soil_moisture >= 80:
        score += 25
    elif soil_moisture >= 60:
        score += 15
    elif soil_moisture >= 40:
        score += 8

    # Slope risk
    if slope >= 35:
        score += 25
    elif slope >= 25:
        score += 15
    elif slope >= 15:
        score += 8

    # Elevation contribution
    if elevation >= 1500:
        score += 10
    elif elevation >= 800:
        score += 5

    # Historical landslide
    if past_landslide:
        score += 10

    # Limit score
    score = min(score, 100)

    # Risk category
    if score >= 70:
        risk_level = "HIGH"
    elif score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "risk_score": score,
        "risk_level": risk_level
    }