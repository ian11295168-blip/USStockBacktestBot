# US Stock Strategy Lab

### AI-Powered U.S. Equity Strategy Backtesting Platform

US Stock Strategy Lab is an interactive Python-based application that transforms natural-language trading strategies into executable rules and evaluates their historical performance.

The project was independently developed to combine quantitative analysis, financial markets, and practical software engineering.

## Key Features

- **AI Strategy Parsing:** Convert English trading instructions into structured trading rules using the OpenAI API.
- **Historical Backtesting:** Evaluate strategies using historical U.S. equity market data.
- **A/B Strategy Comparison:** Compare strategy variations and visualize performance differences.
- **Performance Analytics:** Analyze total return, CAGR, Sharpe ratio, maximum drawdown, and win rate.
- **Detailed Reporting:** Explore annual performance, trade history, and time-segmented analysis.
- **Cloud Deployment:** Access the application through Streamlit Community Cloud.
- **Data Persistence:** Store private strategy states and backtest results using PostgreSQL (Supabase).

## Technology Stack

Python · Pandas · NumPy · Streamlit · OpenAI API · PostgreSQL · Supabase · Git · GitHub

## How It Works

1. Enter a trading strategy in natural language.
2. Review the AI-generated trading rules.
3. Confirm and execute the historical backtest.
4. Analyze performance metrics and equity curves.
5. Compare alternative strategies using A/B testing.

## Example Strategy

Buy AAPL when RSI(14) is below 30. Sell when RSI(14) is above 70. Apply a 7% fixed stop loss and a 15% take profit. Backtest the past five years.

## Live Application

**Live Demo:** Add your public Streamlit URL here.

Visitors can explore the interactive backtesting features through a guest workspace without accessing private strategy records.

## Methodology and Limitations

Backtests are based on historical market data and simulated trading rules. Performance is not a guarantee of future results.

The time-segmented analysis divides an existing backtest into earlier and later periods. It should not be interpreted as independently validated out-of-sample performance unless the strategy was developed without using the later-period data.

## Project Purpose

This project demonstrates the application of mathematical reasoning, data analytics, AI integration, and software development to a real-world financial analysis problem.