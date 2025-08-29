import React, { useState, useEffect } from 'react';
import {
  Container,
  Grid,
  Paper,
  Typography,
  Box,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Alert
} from '@mui/material';
import {
  HeartBroken,
  Security,
  Notifications,
  Timeline,
  Person,
  Warning
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import axios from 'axios';
import io from 'socket.io-client';

interface DashboardData {
  user_info: {
    full_name: string;
    role: string;
    device_id: string;
    is_active: boolean;
  };
  health_summary: {
    total_records: number;
    latest_vitals: any;
    alerts_count: number;
    status: string;
  };
  safety_summary: {
    total_records: number;
    latest_activity: any;
    falls_count: number;
    alerts_count: number;
    status: string;
  };
  alerts_summary: {
    total_alerts: number;
    by_priority: { [key: string]: number };
    unresolved: number;
  };
  reminders_summary: {
    total_reminders: number;
    completed: number;
    pending: number;
    upcoming: number;
  };
  system_status: {
    agents_running: string[];
    system_health: string;
  };
}

const ElderlyDashboard: React.FC = () => {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [realtimeData, setRealtimeData] = useState<any>(null);

  // Get user ID from URL or local storage (for demo, use hardcoded)
  const userId = 1; // In real app, get from auth context

  useEffect(() => {
    fetchDashboardData();
    setupWebSocket();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`/api/v1/dashboard/overview/${userId}?hours=24`);
      setDashboardData(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load dashboard data');
      console.error('Dashboard data fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const setupWebSocket = () => {
    const socket = io('http://localhost:8000');

    socket.on('connect', () => {
      console.log('Connected to WebSocket');
      socket.emit('join', { user_id: userId });
    });

    socket.on('health_update', (data) => {
      console.log('Health update received:', data);
      setRealtimeData(prev => ({ ...prev, health: data }));
    });

    socket.on('safety_update', (data) => {
      console.log('Safety update received:', data);
      setRealtimeData(prev => ({ ...prev, safety: data }));
    });

    socket.on('reminder', (data) => {
      console.log('Reminder received:', data);
      // Show notification
      if (Notification.permission === 'granted') {
        new Notification('Reminder', {
          body: data.message,
          icon: '/favicon.ico'
        });
      }
    });

    socket.on('alert', (data) => {
      console.log('Alert received:', data);
      // Show alert notification
      if (Notification.permission === 'granted') {
        new Notification('Alert', {
          body: data.message,
          icon: '/favicon.ico'
        });
      }
    });

    return () => {
      socket.disconnect();
    };
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'normal': return 'success';
      case 'alert': return 'error';
      case 'warning': return 'warning';
      default: return 'default';
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority.toLowerCase()) {
      case 'critical': return 'error';
      case 'high': return 'error';
      case 'medium': return 'warning';
      case 'low': return 'info';
      default: return 'default';
    }
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Box sx={{ width: '100%', mt: 4 }}>
          <LinearProgress />
          <Typography variant="h6" sx={{ mt: 2, textAlign: 'center' }}>
            Loading dashboard...
          </Typography>
        </Box>
      </Container>
    );
  }

  if (error || !dashboardData) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Alert severity="error">
          {error || 'Failed to load dashboard data'}
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Elderly Care Dashboard
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Person />
          <Typography variant="h6">
            {dashboardData.user_info.full_name}
          </Typography>
          <Chip
            label={dashboardData.user_info.role}
            variant="outlined"
            size="small"
          />
          <Chip
            label={dashboardData.system_status.system_health === 'healthy' ? 'System Online' : 'System Issues'}
            color={dashboardData.system_status.system_health === 'healthy' ? 'success' : 'error'}
            size="small"
          />
        </Box>
      </Box>

      {/* Real-time Updates */}
      {realtimeData && (
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="subtitle2">Real-time Updates:</Typography>
          {realtimeData.health && (
            <Typography variant="body2">
              Heart Rate: {realtimeData.health.vitals?.heart_rate} bpm
            </Typography>
          )}
          {realtimeData.safety && (
            <Typography variant="body2">
              Activity: {realtimeData.safety.movement?.activity}
            </Typography>
          )}
        </Alert>
      )}

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* Health Status */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <HeartBroken color="error" sx={{ mr: 1 }} />
                <Typography variant="h6">Health</Typography>
              </Box>
              <Typography variant="h4" color="primary">
                {dashboardData.health_summary.alerts_count}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Active alerts
              </Typography>
              <Chip
                label={dashboardData.health_summary.status}
                color={getStatusColor(dashboardData.health_summary.status)}
                size="small"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>

        {/* Safety Status */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Security color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6">Safety</Typography>
              </Box>
              <Typography variant="h4" color="primary">
                {dashboardData.safety_summary.falls_count}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Falls detected
              </Typography>
              <Chip
                label={dashboardData.safety_summary.status}
                color={getStatusColor(dashboardData.safety_summary.status)}
                size="small"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>

        {/* Alerts */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Notifications color="warning" sx={{ mr: 1 }} />
                <Typography variant="h6">Alerts</Typography>
              </Box>
              <Typography variant="h4" color="primary">
                {dashboardData.alerts_summary.unresolved}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Unresolved alerts
              </Typography>
              {dashboardData.alerts_summary.by_priority.critical > 0 && (
                <Chip
                  label={`${dashboardData.alerts_summary.by_priority.critical} Critical`}
                  color="error"
                  size="small"
                  sx={{ mt: 1 }}
                />
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Reminders */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Timeline color="secondary" sx={{ mr: 1 }} />
                <Typography variant="h6">Reminders</Typography>
              </Box>
              <Typography variant="h4" color="primary">
                {dashboardData.reminders_summary.pending}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Pending reminders
              </Typography>
              <Typography variant="body2" color="success.main">
                {dashboardData.reminders_summary.completed} completed today
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Detailed Sections */}
      <Grid container spacing={3}>
        {/* Health Details */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Health Monitoring
            </Typography>
            {dashboardData.health_summary.latest_vitals ? (
              <Box>
                <Typography variant="body2">
                  Latest Reading: {new Date(dashboardData.health_summary.latest_vitals.timestamp).toLocaleString()}
                </Typography>
                <Typography variant="body2">
                  Heart Rate: {dashboardData.health_summary.latest_vitals.heart_rate} bpm
                </Typography>
                <Typography variant="body2">
                  Blood Pressure: {dashboardData.health_summary.latest_vitals.blood_pressure}
                </Typography>
                <Typography variant="body2">
                  Glucose: {dashboardData.health_summary.latest_vitals.glucose_level} mg/dL
                </Typography>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No recent health data available
              </Typography>
            )}
          </Paper>
        </Grid>

        {/* Safety Details */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Safety Monitoring
            </Typography>
            {dashboardData.safety_summary.latest_activity ? (
              <Box>
                <Typography variant="body2">
                  Latest Activity: {new Date(dashboardData.safety_summary.latest_activity.timestamp).toLocaleString()}
                </Typography>
                <Typography variant="body2">
                  Movement: {dashboardData.safety_summary.latest_activity.movement_activity}
                </Typography>
                <Typography variant="body2">
                  Location: {dashboardData.safety_summary.latest_activity.location_room}
                </Typography>
                {dashboardData.safety_summary.latest_activity.fall_detected && (
                  <Alert severity="error" sx={{ mt: 1 }}>
                    Fall detected!
                  </Alert>
                )}
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No recent safety data available
              </Typography>
            )}
          </Paper>
        </Grid>

        {/* Priority Alerts */}
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Priority Alerts
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {Object.entries(dashboardData.alerts_summary.by_priority).map(([priority, count]) => (
                count > 0 && (
                  <Chip
                    key={priority}
                    label={`${count} ${priority}`}
                    color={getPriorityColor(priority)}
                    variant="outlined"
                  />
                )
              ))}
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Container>
  );
};

export default ElderlyDashboard;
