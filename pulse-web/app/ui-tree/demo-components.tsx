import React, { type ReactNode } from 'react';

export interface CounterProps {
  count?: number;
  label?: string;
  color?: 'blue' | 'green' | 'red' | 'purple';
  size?: 'sm' | 'md' | 'lg';
  children?: ReactNode;
}

export function Counter({ count = 0, label = 'Count', color = 'blue', size = 'md', children }: CounterProps) {
  const sizeClasses = {
    sm: 'text-sm p-2',
    md: 'text-base p-4',
    lg: 'text-lg p-6'
  };

  const colorClasses = {
    blue: 'bg-blue-50 border-blue-200 text-blue-800',
    green: 'bg-green-50 border-green-200 text-green-800',
    red: 'bg-red-50 border-red-200 text-red-800',
    purple: 'bg-purple-50 border-purple-200 text-purple-800'
  };

  return (
    <div className={`border rounded-lg ${sizeClasses[size]} ${colorClasses[color]}`}>
      <div className="font-semibold">{label}</div>
      <div className="text-2xl font-bold mt-2">{count}</div>
      {children && (
        <div className="mt-3 pt-3 border-t border-current border-opacity-20">
          {children}
        </div>
      )}
    </div>
  );
}

export interface UserCardProps {
  name?: string;
  email?: string;
  avatar?: string;
  role?: string;
  status?: 'online' | 'offline' | 'away';
}

export function UserCard({ 
  name = 'Anonymous User', 
  email = 'user@example.com', 
  avatar, 
  role = 'User', 
  status = 'offline' 
}: UserCardProps) {
  const statusColors = {
    online: 'bg-green-400',
    offline: 'bg-gray-400',
    away: 'bg-yellow-400'
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <div className="flex items-center space-x-3">
        <div className="relative">
          {avatar ? (
            <img src={avatar} alt={name} className="w-12 h-12 rounded-full" />
          ) : (
            <div className="w-12 h-12 rounded-full bg-gray-300 flex items-center justify-center text-gray-600 font-semibold">
              {name.charAt(0).toUpperCase()}
            </div>
          )}
          <div className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full border-2 border-white ${statusColors[status]}`}></div>
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900">{name}</h3>
          <p className="text-sm text-gray-600">{email}</p>
          <p className="text-xs text-gray-500 mt-1">{role}</p>
        </div>
      </div>
    </div>
  );
}

export interface ProgressBarProps {
  value?: number;
  max?: number;
  label?: string;
  color?: 'blue' | 'green' | 'red' | 'purple';
  showPercentage?: boolean;
}

export function ProgressBar({ 
  value = 0, 
  max = 100, 
  label = 'Progress', 
  color = 'blue',
  showPercentage = true 
}: ProgressBarProps) {
  const percentage = Math.round((value / max) * 100);
  
  const colorClasses = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    red: 'bg-red-500',
    purple: 'bg-purple-500'
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex justify-between items-center mb-2">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        {showPercentage && (
          <span className="text-sm text-gray-600">{percentage}%</span>
        )}
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div 
          className={`h-2 rounded-full transition-all duration-300 ${colorClasses[color]}`}
          style={{ width: `${percentage}%` }}
        ></div>
      </div>
      <div className="flex justify-between text-xs text-gray-500 mt-1">
        <span>{value}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

export interface StatusBadgeProps {
  status?: 'success' | 'warning' | 'error' | 'info';
  text?: string;
  size?: 'sm' | 'md' | 'lg';
  pulse?: boolean;
}

export function StatusBadge({ 
  status = 'info', 
  text = 'Status', 
  size = 'md',
  pulse = false 
}: StatusBadgeProps) {
  const statusClasses = {
    success: 'bg-green-100 text-green-800 border-green-200',
    warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    error: 'bg-red-100 text-red-800 border-red-200',
    info: 'bg-blue-100 text-blue-800 border-blue-200'
  };

  const sizeClasses = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-2 text-base'
  };

  return (
    <span 
      className={`
        inline-flex items-center border rounded-full font-medium
        ${statusClasses[status]} 
        ${sizeClasses[size]}
        ${pulse ? 'animate-pulse' : ''}
      `}
    >
      <div className={`w-2 h-2 rounded-full mr-2 ${
        status === 'success' ? 'bg-green-400' :
        status === 'warning' ? 'bg-yellow-400' :
        status === 'error' ? 'bg-red-400' : 'bg-blue-400'
      }`}></div>
      {text}
    </span>
  );
}

export interface MetricCardProps {
  title?: string;
  value?: string | number;
  change?: number;
  trend?: 'up' | 'down' | 'neutral';
  icon?: string;
  children?: ReactNode;
}

export function MetricCard({ 
  title = 'Metric', 
  value = '0', 
  change = 0, 
  trend = 'neutral',
  icon = '📊',
  children
}: MetricCardProps) {
  const trendColors = {
    up: 'text-green-600',
    down: 'text-red-600',
    neutral: 'text-gray-600'
  };

  const trendIcons = {
    up: '↗️',
    down: '↘️',
    neutral: '➡️'
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center">
          <span className="text-2xl mr-3">{icon}</span>
          <div>
            <p className="text-sm font-medium text-gray-600">{title}</p>
            <p className="text-2xl font-bold text-gray-900">{value}</p>
          </div>
        </div>
        {change !== 0 && (
          <div className={`flex items-center ${trendColors[trend]}`}>
            <span className="mr-1">{trendIcons[trend]}</span>
            <span className="text-sm font-medium">{Math.abs(change)}%</span>
          </div>
        )}
      </div>
      {children && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          {children}
        </div>
      )}
    </div>
  );
}

export interface CardProps {
  title?: string;
  subtitle?: string;
  variant?: 'default' | 'primary' | 'success' | 'warning';
  children?: ReactNode;
}

export function Card({ 
  title = 'Card Title', 
  subtitle,
  variant = 'default',
  children 
}: CardProps) {
  const variantClasses = {
    default: 'bg-white border-gray-200',
    primary: 'bg-blue-50 border-blue-200',
    success: 'bg-green-50 border-green-200',
    warning: 'bg-yellow-50 border-yellow-200'
  };

  return (
    <div className={`border rounded-lg p-4 shadow-sm ${variantClasses[variant]}`}>
      <div className="mb-3">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        {subtitle && (
          <p className="text-sm text-gray-600 mt-1">{subtitle}</p>
        )}
      </div>
      <div className="space-y-2">
        {children}
      </div>
    </div>
  );
}

export interface ButtonProps {
  text?: string;
  variant?: 'primary' | 'secondary' | 'success' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  children?: ReactNode;
}

export function Button({ 
  text = 'Button',
  variant = 'primary',
  size = 'md',
  disabled = false,
  children
}: ButtonProps) {
  const variantClasses = {
    primary: 'bg-blue-600 hover:bg-blue-700 text-white',
    secondary: 'bg-gray-600 hover:bg-gray-700 text-white',
    success: 'bg-green-600 hover:bg-green-700 text-white',
    danger: 'bg-red-600 hover:bg-red-700 text-white'
  };

  const sizeClasses = {
    sm: 'px-3 py-1 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg'
  };

  return (
    <button 
      className={`
        rounded font-medium transition-colors
        ${variantClasses[variant]} 
        ${sizeClasses[size]}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:shadow-md'}
      `}
      disabled={disabled}
    >
      {text}
      {children && <span className="ml-2">{children}</span>}
    </button>
  );
}