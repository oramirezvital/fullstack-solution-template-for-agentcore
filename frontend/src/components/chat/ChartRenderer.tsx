"use client"

import { LineChart, Line, BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

/**
 * Chart specification interface matching the backend format
 */
interface ChartDataset {
  label: string
  data: number[]
  color?: string
}

interface ChartData {
  labels: string[]
  datasets: ChartDataset[]
}

interface ChartOptions {
  yAxisLabel?: string
  xAxisLabel?: string
  showLegend?: boolean
  showGrid?: boolean
}

interface ChartSpec {
  type: "chart"
  chartType: "line" | "bar" | "area" | "pie" | "doughnut"
  title: string
  data: ChartData
  options?: ChartOptions
}

/**
 * Transform chart data from backend format to Recharts format
 */
function transformChartData(chartData: ChartData) {
  const { labels, datasets } = chartData
  
  // For line, bar, area charts: transform to array of objects
  if (datasets.length > 0 && datasets[0].data.length === labels.length) {
    return labels.map((label, index) => {
      const dataPoint: Record<string, string | number> = { name: label }
      datasets.forEach(dataset => {
        dataPoint[dataset.label] = dataset.data[index]
      })
      return dataPoint
    })
  }
  
  return []
}

/**
 * Transform data for pie/doughnut charts
 */
function transformPieData(chartData: ChartData) {
  const { labels, datasets } = chartData
  const dataset = datasets[0] // Pie charts typically have one dataset
  
  return labels.map((label, index) => ({
    name: label,
    value: dataset.data[index]
  }))
}

/**
 * Default colors for chart datasets
 */
const DEFAULT_COLORS = [
  '#3fb950', // Green
  '#58a6ff', // Blue
  '#f85149', // Red
  '#d29922', // Yellow
  '#a371f7', // Purple
  '#ff7b72', // Light red
  '#79c0ff', // Light blue
  '#56d364', // Light green
]

/**
 * ChartRenderer Component
 * 
 * Renders interactive charts using Recharts library based on JSON data
 * from the agent's response.
 */
export function ChartRenderer({ chartSpec }: { chartSpec: ChartSpec }) {
  const { chartType, title, data, options = {} } = chartSpec
  const { yAxisLabel, xAxisLabel, showLegend = true, showGrid = true } = options
  
  // Transform data based on chart type
  const chartData = chartType === 'pie' || chartType === 'doughnut' 
    ? transformPieData(data)
    : transformChartData(data)
  
  // Get colors for datasets
  const colors = data.datasets.map((ds, idx) => ds.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length])
  
  return (
    <div className="my-4 bg-white dark:bg-gray-800 p-6 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
      {/* Chart Title */}
      <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">
        {title}
      </h3>
      
      {/* Chart Container */}
      <ResponsiveContainer width="100%" height={400}>
        {chartType === 'line' && (
          <LineChart data={chartData}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
            <XAxis 
              dataKey="name" 
              label={xAxisLabel ? { value: xAxisLabel, position: 'insideBottom', offset: -5 } : undefined}
              tick={{ fontSize: 12 }}
            />
            <YAxis 
              label={yAxisLabel ? { value: yAxisLabel, angle: -90, position: 'insideLeft' } : undefined}
              tick={{ fontSize: 12 }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'white', 
                border: '1px solid #e5e7eb',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            />
            {showLegend && <Legend wrapperStyle={{ fontSize: '12px' }} />}
            {data.datasets.map((dataset, idx) => (
              <Line
                key={dataset.label}
                type="monotone"
                dataKey={dataset.label}
                stroke={colors[idx]}
                strokeWidth={2}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
              />
            ))}
          </LineChart>
        )}
        
        {chartType === 'bar' && (
          <BarChart data={chartData}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
            <XAxis 
              dataKey="name"
              label={xAxisLabel ? { value: xAxisLabel, position: 'insideBottom', offset: -5 } : undefined}
              tick={{ fontSize: 12 }}
            />
            <YAxis 
              label={yAxisLabel ? { value: yAxisLabel, angle: -90, position: 'insideLeft' } : undefined}
              tick={{ fontSize: 12 }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'white', 
                border: '1px solid #e5e7eb',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            />
            {showLegend && <Legend wrapperStyle={{ fontSize: '12px' }} />}
            {data.datasets.map((dataset, idx) => (
              <Bar
                key={dataset.label}
                dataKey={dataset.label}
                fill={colors[idx]}
              />
            ))}
          </BarChart>
        )}
        
        {chartType === 'area' && (
          <AreaChart data={chartData}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
            <XAxis 
              dataKey="name"
              label={xAxisLabel ? { value: xAxisLabel, position: 'insideBottom', offset: -5 } : undefined}
              tick={{ fontSize: 12 }}
            />
            <YAxis 
              label={yAxisLabel ? { value: yAxisLabel, angle: -90, position: 'insideLeft' } : undefined}
              tick={{ fontSize: 12 }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'white', 
                border: '1px solid #e5e7eb',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            />
            {showLegend && <Legend wrapperStyle={{ fontSize: '12px' }} />}
            {data.datasets.map((dataset, idx) => (
              <Area
                key={dataset.label}
                type="monotone"
                dataKey={dataset.label}
                stroke={colors[idx]}
                fill={colors[idx]}
                fillOpacity={0.3}
              />
            ))}
          </AreaChart>
        )}
        
        {(chartType === 'pie' || chartType === 'doughnut') && (
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              labelLine={true}
              label={(entry) => `${entry.name}: ${entry.value}`}
              outerRadius={chartType === 'doughnut' ? 120 : 140}
              innerRadius={chartType === 'doughnut' ? 60 : 0}
              fill="#8884d8"
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
              ))}
            </Pie>
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'white', 
                border: '1px solid #e5e7eb',
                borderRadius: '6px',
                fontSize: '12px'
              }}
            />
            {showLegend && <Legend wrapperStyle={{ fontSize: '12px' }} />}
          </PieChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
