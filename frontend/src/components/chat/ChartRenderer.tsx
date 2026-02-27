"use client"

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  ChartOptions as ChartJSOptions
} from 'chart.js'
import { Line, Bar, Pie, Doughnut } from 'react-chartjs-2'

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

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
 * Transform chart data from backend format to Chart.js format
 * 
 * @param chartData - Backend chart data format
 * @param chartType - Type of chart being rendered
 * @returns Chart.js compatible data object
 */
function transformToChartJsFormat(chartData: ChartData, chartType: string) {
  const { labels, datasets } = chartData
  
  // For pie and doughnut charts
  if (chartType === 'pie' || chartType === 'doughnut') {
    const dataset = datasets[0] // Pie charts typically have one dataset
    return {
      labels,
      datasets: [{
        label: dataset.label,
        data: dataset.data,
        backgroundColor: labels.map((_, idx) => 
          dataset.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length]
        ),
        borderColor: '#ffffff',
        borderWidth: 2
      }]
    }
  }
  
  // For line, bar, and area charts
  return {
    labels,
    datasets: datasets.map((dataset, idx) => {
      const color = dataset.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length]
      
      return {
        label: dataset.label,
        data: dataset.data,
        backgroundColor: chartType === 'area' ? `${color}4D` : color, // 30% opacity for area
        borderColor: color,
        borderWidth: 2,
        fill: chartType === 'area',
        tension: 0.4, // Smooth curves for line/area charts
        pointRadius: 4,
        pointHoverRadius: 6
      }
    })
  }
}

/**
 * Get Chart.js options configuration
 * 
 * @param options - Chart options from backend
 * @returns Chart.js options object
 */
function getChartOptions(options: ChartOptions): ChartJSOptions {
  const { yAxisLabel, xAxisLabel, showLegend = true, showGrid = true } = options
  
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: showLegend,
        position: 'top' as const,
        labels: {
          color: '#6b7280',
          font: {
            size: 12
          }
        }
      },
      title: {
        display: false // We render title separately for better styling control
      },
      tooltip: {
        backgroundColor: 'white',
        titleColor: '#1f2937',
        bodyColor: '#1f2937',
        borderColor: '#e5e7eb',
        borderWidth: 1,
        padding: 12,
        displayColors: true,
        boxPadding: 6
      }
    },
    scales: {
      x: {
        display: true,
        title: {
          display: !!xAxisLabel,
          text: xAxisLabel || '',
          color: '#6b7280',
          font: {
            size: 12
          }
        },
        grid: {
          display: showGrid,
          color: '#e5e7eb'
        },
        ticks: {
          color: '#6b7280',
          font: {
            size: 12
          }
        }
      },
      y: {
        display: true,
        title: {
          display: !!yAxisLabel,
          text: yAxisLabel || '',
          color: '#6b7280',
          font: {
            size: 12
          }
        },
        grid: {
          display: showGrid,
          color: '#e5e7eb'
        },
        ticks: {
          color: '#6b7280',
          font: {
            size: 12
          }
        }
      }
    }
  }
}

/**
 * Get Chart.js options for pie/doughnut charts
 * 
 * @param options - Chart options from backend
 * @returns Chart.js options object for pie/doughnut
 */
function getPieChartOptions(options: ChartOptions): ChartJSOptions {
  const { showLegend = true } = options
  
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: showLegend,
        position: 'right' as const,
        labels: {
          color: '#6b7280',
          font: {
            size: 12
          },
          padding: 15
        }
      },
      tooltip: {
        backgroundColor: 'white',
        titleColor: '#1f2937',
        bodyColor: '#1f2937',
        borderColor: '#e5e7eb',
        borderWidth: 1,
        padding: 12
      }
    }
  }
}

/**
 * ChartRenderer Component
 * 
 * Renders interactive charts using Chart.js library based on JSON data
 * from the agent's response.
 * 
 * @param chartSpec - Chart specification from backend
 */
export function ChartRenderer({ chartSpec }: { chartSpec: ChartSpec }) {
  const { chartType, title, data, options = {} } = chartSpec
  
  // Transform data to Chart.js format
  const chartData = transformToChartJsFormat(data, chartType)
  
  // Get appropriate options based on chart type
  const chartOptions = (chartType === 'pie' || chartType === 'doughnut')
    ? getPieChartOptions(options)
    : getChartOptions(options)
  
  return (
    <div className="my-4 bg-white dark:bg-gray-800 p-6 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
      {/* Chart Title */}
      <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">
        {title}
      </h3>
      
      {/* Chart Container */}
      <div style={{ height: '400px', width: '100%' }}>
        {chartType === 'line' && (
          <Line data={chartData} options={chartOptions as any} />
        )}
        
        {chartType === 'bar' && (
          <Bar data={chartData} options={chartOptions as any} />
        )}
        
        {chartType === 'area' && (
          <Line data={chartData} options={chartOptions as any} />
        )}
        
        {chartType === 'pie' && (
          <Pie data={chartData} options={chartOptions as any} />
        )}
        
        {chartType === 'doughnut' && (
          <Doughnut data={chartData} options={chartOptions as any} />
        )}
      </div>
    </div>
  )
}
