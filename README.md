Morning Dash Smart Mirror AI-based Smart Mirror for Morning Routine
Assistance

Overview Morning Dash is a smart mirror system designed to assist users
during their morning routine. The system integrates multiple services
such as facial recognition, schedule management, weather information,
and commuting prediction to provide a personalized morning briefing.

The project was developed as part of a university engineering
competition using Raspberry Pi and Python-based web technologies.

System Architecture The system integrates several modules to provide an
intelligent morning dashboard:

-   Facial recognition for user identification
-   Schedule synchronization using calendar data
-   Weather information from OpenWeather API
-   Public transportation information using transportation APIs
-   AI-based commuting probability analysis
-   Web-based dashboard for displaying information

Key Features

Face Recognition The system identifies the user using a camera and
facial recognition engine to provide personalized information.

Morning Briefing After recognizing the user, the system automatically
provides a briefing including weather, schedule, and commute status.

Commute Probability Prediction The system analyzes transportation data
and estimates the probability of successful arrival based on traffic and
transit conditions.

Weather Monitoring Weather data is collected from external APIs and
displayed on the mirror dashboard.

Checklist System Users can manage daily tasks and items to bring before
leaving home.

Dashboard Interface A web-based dashboard provides real-time information
including:

-   Weather conditions
-   Schedule events
-   Commute information
-   Daily checklist

System Components

Hardware - Raspberry Pi - Camera module - Display (Smart Mirror Screen)

Software - Python - Flask Web Framework - Streamlit - OpenCV - Various
external APIs (weather, transportation)

Project Structure

Morning_Dash │ ├─ app.py ├─ db.py ├─ register.py ├─ streamlit_app.py │
├─ cv │ └─ condition_cv.py │ ├─ logic │ ├─ briefing.py │ ├─
commute_probability.py │ ├─ face_engine.py │ ├─ policy.py │ └─
system_controller.py │ ├─ services │ ├─ calendar_core.py │ ├─
kakao_local.py │ ├─ kakao_mobility.py │ ├─ openweather.py │ ├─ subway.py
│ └─ tago.py │ ├─ web │ ├─ static │ │ ├─ app.js │ │ └─ style.css │ └─
templates │ ├─ dashboard.html │ ├─ weather.html │ ├─ traffic.html │ └─
checklist.html

My Contribution

-   Raspberry Pi based smart mirror system development
-   Python backend development
-   Integration of external APIs for weather and transportation data
-   Face recognition system implementation
-   Dashboard UI development
-   System integration and testing

Development Environment

Hardware - Raspberry Pi

Software - Python - Flask - Streamlit - OpenCV

Future Improvements

-   More advanced AI-based commute prediction
-   Voice interaction features
-   Mobile application integration
-   Cloud-based user data synchronization
