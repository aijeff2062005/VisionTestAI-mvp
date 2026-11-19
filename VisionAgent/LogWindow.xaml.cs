using System.Windows;
using VisionAgent.Services;

namespace VisionAgent;

public partial class LogWindow : Window
{
    public LogWindow(AgentLogWriter logs)
    {
        InitializeComponent();
        LogList.ItemsSource = logs.ReadRecent(500);
    }

    private void Close_Click(object sender, RoutedEventArgs e) => Close();
}
