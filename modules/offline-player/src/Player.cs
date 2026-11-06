using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Collections.Generic;
using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using System.Xml.Linq;
using Microsoft.Win32;
using System.Windows.Documents;
using System.Web.Script.Serialization;
using System.Security.Cryptography;

namespace ClassroomPlayer {
 public class Word { public double Start, End; public string Text; }
  public class Cue { public double Start, End; public string Text; public bool PauseSafe=true; public List<Word> Words=new List<Word>(); }
 public class CaptionBox : RichTextBox {
  public CaptionBox(){IsReadOnly=true;IsDocumentEnabled=true;BorderThickness=new Thickness(0);Background=Brushes.Transparent;Padding=new Thickness(0);Document.PagePadding=new Thickness(0);VerticalScrollBarVisibility=ScrollBarVisibility.Auto;Cursor=Cursors.IBeam;}
  public string Text {get{return new TextRange(Document.ContentStart,Document.ContentEnd).Text.TrimEnd('\r','\n');}set{Document.Blocks.Clear();Document.Blocks.Add(new Paragraph(new Run(value)){Margin=new Thickness(0),TextAlignment=TextAlignment.Center});}}
  public TextWrapping TextWrapping{get;set;}
  public TextAlignment TextAlignment{get;set;}
 }
 public static class Subtitles {
  public static List<Cue> ReadJson(string path,string audio){
   var serializer=new JavaScriptSerializer{MaxJsonLength=16000000};
   var doc=(Dictionary<string,object>)serializer.DeserializeObject(File.ReadAllText(path,Encoding.UTF8));
   object hash;
   if(doc.TryGetValue("audio_sha256",out hash)&&audio!="") {using(var stream=File.OpenRead(audio))using(var sha=SHA256.Create()){string actual=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();if(actual!=(string)hash)throw new InvalidDataException("字幕与音频哈希不符。");}}
   Func<object,double> ms=o=>{if(o==null)throw new InvalidDataException("缺少时间。");double n=Convert.ToDouble(o,CultureInfo.InvariantCulture)/1000;if(double.IsNaN(n)||double.IsInfinity(n)||n<0)throw new InvalidDataException("时间非法。");return n;};
   var rows=(object[])doc["segments"]; var cues=new List<Cue>();
   foreach(Dictionary<string,object> row in rows){var c=new Cue{Start=ms(row["start_ms"]),End=ms(row["end_ms"]),Text=(string)row["text"]};if(c.End<=c.Start||string.IsNullOrWhiteSpace(c.Text)||(cues.Count>0&&c.Start<cues[cues.Count-1].End))throw new InvalidDataException("句子时间非法或重叠。");object value;if(row.TryGetValue("words",out value)&&value!=null){foreach(Dictionary<string,object> w in (object[])value){string text=(string)w["word"];double a=w["start_ms"]==null?-1:ms(w["start_ms"]),b=w["end_ms"]==null?-1:ms(w["end_ms"]);if((a>=0&&(a<c.Start||a>c.End))||(b>=0&&(b<c.Start||b>c.End))||(a>=0&&b>=0&&b<=a)||(a>=0&&c.Words.Count>0&&c.Words[c.Words.Count-1].End>a))throw new InvalidDataException("词时间越过句界。");c.Words.Add(new Word{Start=a,End=b,Text=text});}if(Regex.Replace(c.Text.Trim(),@"\s+"," ")!=string.Join(" ",c.Words.Select(w=>w.Text)))c.Words.Clear();}cues.Add(c);}
   if(cues.Count==0)throw new InvalidDataException("没有字幕。");object policy;if(doc.TryGetValue("sentence_policy",out policy)&&(string)policy=="unresolved")foreach(var c in cues)c.PauseSafe=false;return cues;
  }
  public static List<Cue> Read(string path) {
   string text=File.ReadAllText(path, Encoding.UTF8).Replace("\r", "").TrimStart('\uFEFF');
   var result=new List<Cue>();
   foreach(string block in Regex.Split(text.Trim(), @"\n\s*\n")) {
    var m=Regex.Match(block, @"(?m)^(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})[^\n]*\n([\s\S]+)$");
    if(!m.Success) continue;
    Func<int,double> time=i=>int.Parse(m.Groups[i].Value)*3600+int.Parse(m.Groups[i+1].Value)*60+int.Parse(m.Groups[i+2].Value)+int.Parse(m.Groups[i+3].Value)/1000.0;
    double start=time(1),end=time(5);
    if(end<=start) continue;
    string line=Regex.Replace(m.Groups[9].Value,@"</?(?:b|i|u|font)(?:\s[^>]*)?>", "", RegexOptions.IgnoreCase).Trim();
    result.Add(new Cue { Start=start, End=end, Text=line });
   }
   result=result.OrderBy(c=>c.Start).ToList();
   if(result.Count==0) throw new InvalidDataException("没有读到有效的 SRT 字幕，请检查文件格式与 UTF-8 编码。");
   for(int i=1;i<result.Count;i++) if(result[i].Start<result[i-1].End) throw new InvalidDataException("字幕时间重叠，请先在字幕工作台修订。");
   return result;
  }
 }
 public class Player : Window {
  MediaElement media=new MediaElement(); DispatcherTimer timer=new DispatcherTimer();
  TextBlock filename=new TextBlock(),hint=new TextBlock(),clock=new TextBlock(); CaptionBox caption=new CaptionBox(); List<Run> wordRuns=new List<Run>(); int litWord=-1;
  Slider progress=new Slider(),volume=new Slider(); ComboBox rate=new ComboBox();
  Button play,loopButton,pauseButton,showButton; List<Cue> cues=new List<Cue>();
  bool playing,ready,updating,dragging,visible=true,loop,autoPause,full;
  int active=-1,loopIndex=-1,pausedCue=-1,loopReturns; double lastPosition; string audioPath="",subtitlePath="";
  readonly string settingsPath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CETClassroomPlayer","state.xml");
  Dictionary<string,double> positions=new Dictionary<string,double>(StringComparer.OrdinalIgnoreCase);
  Grid root=new Grid(); Border subtitleArea; WindowStyle oldStyle; ResizeMode oldResize; WindowState oldState;
  bool launching;
  public Player(string[] args, bool splash=true) {
   Title="听力课堂"; Width=1060; Height=720; MinWidth=760; MinHeight=540;
   WindowStartupLocation=WindowStartupLocation.CenterScreen; Background=Brush("#FCF6EE"); Foreground=Brush("#293F3B");
   FontFamily=new FontFamily("Microsoft YaHei UI"); FontSize=14; AllowDrop=true;
   RenderOptions.ProcessRenderMode=System.Windows.Interop.RenderMode.SoftwareOnly;
   root.Margin=new Thickness(32,24,32,24); Content=root;
   foreach(var h in new[]{GridLength.Auto,new GridLength(1,GridUnitType.Star),GridLength.Auto,GridLength.Auto}) root.RowDefinitions.Add(new RowDefinition{Height=h});
   var top=new DockPanel(); Grid.SetRow(top,0); root.Children.Add(top);
   var open=Button("打开音频",()=>OpenAudioDialog()); DockPanel.SetDock(open,Dock.Right); top.Children.Add(open);
   var sub=Button("选择字幕",()=>OpenSubtitleDialog()); DockPanel.SetDock(sub,Dock.Right); top.Children.Add(sub);
   var titles=new StackPanel();
   var identity=new StackPanel{Orientation=Orientation.Horizontal,Margin=new Thickness(0,0,0,8)};
   identity.Children.Add(new Border{CornerRadius=new CornerRadius(10),Background=Brush("#327B68"),Padding=new Thickness(11,5,11,5),Child=new TextBlock{Text="Learn with Adam",FontFamily=new FontFamily("Times New Roman"),FontSize=17,FontWeight=FontWeights.Normal,Foreground=Brushes.White}});
   identity.Children.Add(new TextBlock{Text="听力课堂",FontSize=14,Foreground=Brush("#697D76"),Margin=new Thickness(12,0,0,0),VerticalAlignment=VerticalAlignment.Center});
   titles.Children.Add(identity);
   filename.Text="拖入 MP3，开始听力课堂"; filename.FontSize=20; filename.FontWeight=FontWeights.SemiBold; filename.TextTrimming=TextTrimming.CharacterEllipsis; titles.Children.Add(filename); top.Children.Add(titles);
   subtitleArea=new Border{Background=Brush("#FFFFFF"),BorderBrush=Brush("#E2E6D9"),BorderThickness=new Thickness(2),CornerRadius=new CornerRadius(22),Margin=new Thickness(0,30,0,22),Padding=new Thickness(34),Cursor=Cursors.Arrow,Focusable=true};
   Grid.SetRow(subtitleArea,1); root.Children.Add(subtitleArea);
   var cg=new Grid(); subtitleArea.Child=cg; caption.Text="把音频拖到这里\n同名 JSON / SRT 字幕自动加载"; caption.FontSize=34; caption.TextWrapping=TextWrapping.Wrap; caption.TextAlignment=TextAlignment.Center; caption.VerticalAlignment=VerticalAlignment.Center; var scroll=new ScrollViewer{VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,VerticalContentAlignment=VerticalAlignment.Center,Content=caption}; cg.Children.Add(scroll);
   subtitleArea.ToolTip="拖动或双击字幕文字可选词；使用显隐按钮或 H 控制字幕";
   var timeline=new Grid(); timeline.ColumnDefinitions.Add(new ColumnDefinition()); timeline.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto}); Grid.SetRow(timeline,2); root.Children.Add(timeline);
   progress.Minimum=0; progress.Maximum=1; progress.IsMoveToPointEnabled=true; progress.VerticalAlignment=VerticalAlignment.Center; progress.Margin=new Thickness(0,0,18,0); timeline.Children.Add(progress);
   progress.PreviewMouseLeftButtonDown+=(s,e)=>dragging=true;
   progress.PreviewMouseLeftButtonUp+=(s,e)=>{dragging=false; Seek(progress.Value);};
   progress.LostMouseCapture+=(s,e)=>{if(dragging){dragging=false;Seek(progress.Value);}};
   progress.ValueChanged+=(s,e)=>{if(!updating&&!dragging) Seek(progress.Value);};
   clock.Text="00:00 / 00:00"; clock.VerticalAlignment=VerticalAlignment.Center; clock.Foreground=Brush("#697D76"); Grid.SetColumn(clock,1); timeline.Children.Add(clock);
   var bottom=new StackPanel{Margin=new Thickness(0,16,0,0)}; Grid.SetRow(bottom,3); root.Children.Add(bottom);
   var primary=new WrapPanel{HorizontalAlignment=HorizontalAlignment.Center}; bottom.Children.Add(primary);
   primary.Children.Add(Button("上一句",()=>MoveCue(-1))); primary.Children.Add(Button("−15 秒",()=>Seek(media.Position.TotalSeconds-15)));
   play=Button("播放",()=>TogglePlay()); play.MinWidth=100; play.Background=Brush("#327B68"); play.Foreground=Brush("#FFFFFF"); primary.Children.Add(play);
   primary.Children.Add(Button("+15 秒",()=>Seek(media.Position.TotalSeconds+15))); primary.Children.Add(Button("下一句",()=>MoveCue(1)));
   loopButton=Button("单句循环：关",()=>{loop=!loop; if(loop) {autoPause=false;loopIndex=CurrentOrNext();} UpdateModes();}); primary.Children.Add(loopButton);
   var secondary=new WrapPanel{HorizontalAlignment=HorizontalAlignment.Center,Margin=new Thickness(0,12,0,0)}; bottom.Children.Add(secondary);
   showButton=Button("隐藏字幕",()=>ToggleSubtitles()); secondary.Children.Add(showButton);
   pauseButton=Button("句末暂停：关",()=>{if(cues.Any(c=>!c.PauseSafe)){hint.Text="此字幕断句尚未完成，请先在工作台审核修订。";return;}autoPause=!autoPause;loop=false;pausedCue=-1;UpdateModes();}); secondary.Children.Add(pauseButton);
   secondary.Children.Add(Label("速度")); rate.Width=72; rate.Margin=new Thickness(4); rate.VerticalContentAlignment=VerticalAlignment.Center;
   foreach(double n in new[]{0.75,1.0,1.25,1.5}) rate.Items.Add(n.ToString("0.##",CultureInfo.InvariantCulture)+"×"); rate.SelectedIndex=1; rate.SelectionChanged+=(s,e)=>{media.SpeedRatio=new[]{0.75,1.0,1.25,1.5}[rate.SelectedIndex];}; secondary.Children.Add(rate);
   secondary.Children.Add(Button("A−",()=>{caption.FontSize=Math.Max(22,caption.FontSize-4);})); secondary.Children.Add(Button("A+",()=>{caption.FontSize=Math.Min(64,caption.FontSize+4);}));
   secondary.Children.Add(Label("音量")); volume.Width=90;volume.Minimum=0;volume.Maximum=1;volume.Value=0.8;volume.VerticalAlignment=VerticalAlignment.Center;volume.ValueChanged+=(s,e)=>media.Volume=volume.Value;secondary.Children.Add(volume);
   secondary.Children.Add(Button("全屏",()=>ToggleFull()));
   hint.Text="空格 播放/暂停 · ← → 切句 · H 字幕 · F11 全屏 · 拖选文字讲解 · 按钮 / H 显隐"; hint.FontSize=12;hint.Foreground=Brush("#697D76");hint.TextAlignment=TextAlignment.Center;hint.TextWrapping=TextWrapping.Wrap;hint.Margin=new Thickness(0,14,0,0);bottom.Children.Add(hint);
   media.LoadedBehavior=MediaState.Manual;media.UnloadedBehavior=MediaState.Close;media.Visibility=Visibility.Collapsed;root.Children.Add(media);media.Volume=volume.Value;
   media.MediaOpened+=(s,e)=>{ready=true;progress.Maximum=media.NaturalDuration.HasTimeSpan?media.NaturalDuration.TimeSpan.TotalSeconds:1; double saved; if(positions.TryGetValue(AudioKey(),out saved)&&saved<progress.Maximum-2)Seek(saved); media.SpeedRatio=new[]{0.75,1.0,1.25,1.5}[rate.SelectedIndex];UpdateCaption();};
   media.MediaFailed+=(s,e)=>{ready=false;SetPlaying(false);hint.Text="音频无法播放："+e.ErrorException.Message+"。请在制作电脑检查编码或转换为标准 MP3。";};
   media.MediaEnded+=(s,e)=>{if(loop&&loopIndex>=0){Seek(cues[loopIndex].Start);media.Play();}else{SetPlaying(false);Seek(0);}};
   timer.Interval=TimeSpan.FromMilliseconds(60);timer.Tick+=(s,e)=>Tick();timer.Start();
   Drop+=(s,e)=>{if(launching)return;if(e.Data.GetDataPresent(DataFormats.FileDrop))OpenFiles((string[])e.Data.GetData(DataFormats.FileDrop));};
   PreviewKeyDown+=Keys; Closing+=(s,e)=>{Remember();SaveSettings();media.Close();};
   LoadSettings(); launching=splash; Loaded+=(s,e)=>{Action enter=()=>{launching=false;if(args.Length>0)OpenFiles(args);};if(splash){var host=new Grid();Content=host;root.Visibility=Visibility.Collapsed;host.Children.Add(root);var intro=new LoadingScene();host.Children.Add(intro);intro.Start(()=>{intro.Dispose();host.Children.Remove(intro);root.Visibility=Visibility.Visible;enter();});Closed+=(a,b)=>intro.Dispose();}else enter();};
  }
  static SolidColorBrush Brush(string s){return (SolidColorBrush)new BrushConverter().ConvertFromString(s);}
  Button Button(string text,Action action){var b=new Button{Content=text,Padding=new Thickness(14,10,14,10),Margin=new Thickness(4),MinHeight=42,Background=Brush("#E8EEE6"),BorderThickness=new Thickness(0),Cursor=Cursors.Hand};var border=new FrameworkElementFactory(typeof(Border));border.SetValue(Border.CornerRadiusProperty,new CornerRadius(12));border.SetBinding(Border.BackgroundProperty,new System.Windows.Data.Binding("Background"){RelativeSource=new System.Windows.Data.RelativeSource(System.Windows.Data.RelativeSourceMode.TemplatedParent)});border.SetValue(Border.PaddingProperty,b.Padding);var presenter=new FrameworkElementFactory(typeof(ContentPresenter));presenter.SetValue(ContentPresenter.HorizontalAlignmentProperty,HorizontalAlignment.Center);presenter.SetValue(ContentPresenter.VerticalAlignmentProperty,VerticalAlignment.Center);border.AppendChild(presenter);b.Template=new ControlTemplate(typeof(Button)){VisualTree=border};b.MouseEnter+=(s,e)=>b.Opacity=0.82;b.MouseLeave+=(s,e)=>b.Opacity=1;b.Click+=(s,e)=>{action();Keyboard.Focus(subtitleArea);};return b;}
  TextBlock Label(string text){return new TextBlock{Text=text,VerticalAlignment=VerticalAlignment.Center,Margin=new Thickness(10,0,4,0)};}
  string AudioKey(){if(!File.Exists(audioPath))return audioPath; var f=new FileInfo(audioPath);return audioPath+"|"+f.Length+"|"+f.LastWriteTimeUtc.Ticks;}
  void Remember(){if(ready)positions[AudioKey()]=media.Position.TotalSeconds;}
  void OpenAudioDialog(){var d=new OpenFileDialog{Filter="音频文件|*.mp3;*.m4a;*.wav;*.aac|所有文件|*.*"};if(d.ShowDialog()==true)OpenAudio(d.FileName);}
  void OpenSubtitleDialog(){if(audioPath==""){hint.Text="请先打开音频，再选择对应字幕。";return;}var d=new OpenFileDialog{Filter="字幕文件|*.json;*.srt"};if(d.ShowDialog()==true)LoadSubtitle(d.FileName);}
  void OpenFiles(string[] paths){string audio=paths.FirstOrDefault(p=>new[]{".mp3",".m4a",".wav",".aac"}.Contains(Path.GetExtension(p).ToLowerInvariant()));if(audio!=null)OpenAudio(audio);string sub=paths.FirstOrDefault(p=>Path.GetExtension(p).Equals(".json",StringComparison.OrdinalIgnoreCase))??paths.FirstOrDefault(p=>Path.GetExtension(p).Equals(".srt",StringComparison.OrdinalIgnoreCase));if(sub!=null){if(audioPath=="")hint.Text="请同时拖入音频，或先打开音频。";else LoadSubtitle(sub);}}
  void OpenAudio(string path){try{if(!File.Exists(path))throw new FileNotFoundException("找不到音频文件。");Remember();SaveSettings();media.Close();ready=false;SetPlaying(false);audioPath=Path.GetFullPath(path);filename.Text=Path.GetFileName(path);filename.ToolTip=audioPath;cues.Clear();subtitlePath="";active=-1;loopIndex=-1;pausedCue=-1;lastPosition=0;loop=false;autoPause=false;UpdateModes();media.Source=new Uri(audioPath);media.Play();media.Pause();string sub=Path.ChangeExtension(audioPath,".json");if(!File.Exists(sub))sub=Path.ChangeExtension(audioPath,".srt");if(File.Exists(sub))LoadSubtitle(sub);else{caption.Text="此音频尚未加载字幕";hint.Text="音频可直接播放；将同名 JSON / SRT 放在音频旁边，或点击“选择字幕”。";} }catch(Exception ex){hint.Text=ex.Message;}}
  void LoadSubtitle(string path){try{var loaded=Path.GetExtension(path).ToLowerInvariant()==".json"?Subtitles.ReadJson(path,audioPath):Subtitles.Read(path);cues=loaded;subtitlePath=path;active=-1;loopIndex=-1;pausedCue=-1;hint.Text="已加载 "+cues.Count+" 句 · "+(cues.Any(c=>c.Words.Count>0)?"真实词轴高亮":"普通字幕（无词轴）")+" · 拖选文字可选词，按钮 / H 显隐";UpdateCaption();}catch(Exception ex){hint.Text="字幕未加载："+ex.Message;}}
  int Find(double t){int low=0,high=cues.Count-1;while(low<=high){int mid=(low+high)/2;if(cues[mid].Start<=t)low=mid+1;else high=mid-1;}return high>=0&&t<cues[high].End?high:-1;}
  int CurrentOrNext(){int i=Find(media.Position.TotalSeconds);if(i>=0)return i;int next=cues.FindIndex(c=>c.Start>=media.Position.TotalSeconds);return next<0?cues.Count-1:next;}
  void SetPlaying(bool value){playing=value;play.Content=value?"暂停":"播放";}
  void TogglePlay(){if(!ready){if(audioPath=="")OpenAudioDialog();return;}if(playing){media.Pause();SetPlaying(false);}else{if(autoPause&&pausedCue>=0){int next=pausedCue+1;if(next<cues.Count)Seek(cues[next].Start);pausedCue=-1;}media.Play();SetPlaying(true);}}
  void Seek(double value){if(!ready)return;value=Math.Max(0,Math.Min(progress.Maximum,value));media.Position=TimeSpan.FromSeconds(value);lastPosition=value;pausedCue=-1;if(loop)loopIndex=CurrentOrNext();UpdateCaption();}
  void MoveCue(int direction){if(!ready||cues.Count==0){hint.Text="切句需要先加载 SRT 字幕。";return;}int current=Find(media.Position.TotalSeconds);int i;if(current>=0)i=current+direction;else{int next=cues.FindIndex(c=>c.Start>media.Position.TotalSeconds);if(next<0)next=cues.Count;i=direction>0?next:next-1;}i=Math.Max(0,Math.Min(cues.Count-1,i));Seek(cues[i].Start);loopIndex=i;media.Play();SetPlaying(true);}
  void ToggleSubtitles(){visible=!visible;showButton.Content=visible?"隐藏字幕":"显示字幕";UpdateCaption();}
  void UpdateCaption(){active=Find(media.Position.TotalSeconds);wordRuns.Clear();litWord=-1;caption.Text=!visible?"字幕已隐藏 · 点击“显示字幕”按钮":cues.Count==0?(audioPath==""?"把音频拖到这里\n同名 JSON / SRT 字幕将自动加载":"此音频尚未加载字幕"):active>=0?cues[active].Text:"…";caption.Foreground=Brush(visible?"#293F3B":"#94A3B8");if(visible&&active>=0&&cues[active].Words.Count>0){var p=new Paragraph{Margin=new Thickness(0),TextAlignment=TextAlignment.Center};foreach(var w in cues[active].Words){if(wordRuns.Count>0)p.Inlines.Add(new Run(" "));var run=new Run(w.Text);wordRuns.Add(run);p.Inlines.Add(run);}caption.Document.Blocks.Clear();caption.Document.Blocks.Add(p);}Highlight();}
  void Highlight(){if(!visible||active<0||wordRuns.Count==0)return;double t=media.Position.TotalSeconds;int i=cues[active].Words.FindIndex(w=>w.Start>=0&&w.End>w.Start&&w.Start<=t&&t<w.End);if(i==litWord)return;if(litWord>=0){wordRuns[litWord].Background=Brushes.Transparent;wordRuns[litWord].Foreground=Foreground;}litWord=i;if(i>=0){wordRuns[i].Background=Brush("#D6EDE1");wordRuns[i].Foreground=Brush("#246D5B");}}
  void UpdateModes(){if(cues.Count==0){loop=false;autoPause=false;}loopButton.Content="单句循环："+(loop?"开":"关");pauseButton.Content="句末暂停："+(autoPause?"开":"关");loopButton.Background=Brush(loop?"#D6EDE1":"#E8EEE6");pauseButton.Background=Brush(autoPause?"#D6EDE1":"#E8EEE6");}
  void Tick(){if(!ready)return;double t=media.Position.TotalSeconds;
   if(playing&&loop&&loopIndex>=0&&loopIndex<cues.Count&&t>=cues[loopIndex].End){int keep=loopIndex;Seek(cues[keep].Start);loopIndex=keep;loopReturns++;t=cues[keep].Start;}
   else if(playing&&autoPause){int ended=cues.FindIndex(c=>c.End>lastPosition&&c.End<=t);if(ended>=0){media.Pause();SetPlaying(false);media.Position=TimeSpan.FromSeconds(Math.Max(cues[ended].Start,cues[ended].End-0.02));t=media.Position.TotalSeconds;pausedCue=ended;}}
   lastPosition=t;if(!dragging){updating=true;progress.Value=t;updating=false;}clock.Text=Format(t)+" / "+Format(progress.Maximum);int i=Find(t);if(i!=active)UpdateCaption();Highlight();}
  static string Format(double s){var t=TimeSpan.FromSeconds(Math.Max(0,s));return ((int)t.TotalMinutes).ToString("00")+":"+t.Seconds.ToString("00");}
  void ToggleFull(){if(!full){oldStyle=WindowStyle;oldResize=ResizeMode;oldState=WindowState;WindowStyle=WindowStyle.None;ResizeMode=ResizeMode.NoResize;WindowState=WindowState.Maximized;}else{WindowState=WindowState.Normal;WindowStyle=oldStyle;ResizeMode=oldResize;WindowState=oldState;}full=!full;}
  void Keys(object sender,KeyEventArgs e){if(launching){e.Handled=true;return;}if(e.OriginalSource is Slider||e.OriginalSource is ComboBox||e.OriginalSource is ComboBoxItem)return;switch(e.Key){case Key.Space:TogglePlay();break;case Key.Left:MoveCue(-1);break;case Key.Right:MoveCue(1);break;case Key.H:ToggleSubtitles();break;case Key.F11:ToggleFull();break;case Key.Escape:if(full)ToggleFull();break;default:return;}e.Handled=true;}
  void LoadSettings(){try{if(!File.Exists(settingsPath))return;var x=XElement.Load(settingsPath);double n;if(double.TryParse((string)x.Attribute("volume"),NumberStyles.Float,CultureInfo.InvariantCulture,out n))volume.Value=Math.Max(0,Math.Min(1,n));if(double.TryParse((string)x.Attribute("font"),NumberStyles.Float,CultureInfo.InvariantCulture,out n))caption.FontSize=Math.Max(22,Math.Min(64,n));int r;if(int.TryParse((string)x.Attribute("rate"),out r)&&r>=0&&r<4)rate.SelectedIndex=r;foreach(var p in x.Elements("audio")){if(double.TryParse((string)p.Attribute("position"),NumberStyles.Float,CultureInfo.InvariantCulture,out n)&&n>=0&&n<604800)positions[(string)p.Attribute("key")]=n;}}catch{hint.Text="上次设置无法读取，已使用默认设置。";}}
  void SaveSettings(){try{Directory.CreateDirectory(Path.GetDirectoryName(settingsPath));var x=new XElement("settings",new XAttribute("volume",volume.Value),new XAttribute("font",caption.FontSize),new XAttribute("rate",rate.SelectedIndex));foreach(var p in positions.Take(200))x.Add(new XElement("audio",new XAttribute("key",p.Key),new XAttribute("position",p.Value)));string temp=settingsPath+".tmp";x.Save(temp);if(File.Exists(settingsPath))File.Replace(temp,settingsPath,null);else File.Move(temp,settingsPath);}catch{hint.Text="设置未能保存；播放不受影响。";}}
  static void Check(bool condition,string message){if(!condition)throw new Exception(message);}
  void Smoke(string audio,string srt,string report){
   var checks=new List<string>();var started=DateTime.UtcNow;int step=0;double from=0;var test=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(350)};
   Action<Exception> finish=ex=>{test.Stop();File.WriteAllText(report,(ex==null?"PASS":"FAIL "+ex.Message)+"\n"+string.Join("\n",checks),Encoding.UTF8);Close();};
   test.Tick+=(s,e)=>{try{if((DateTime.UtcNow-started).TotalSeconds>25)throw new Exception("native media timed out: "+hint.Text);
    if(step==0){OpenAudio(audio);LoadSubtitle(srt);step++;}
    else if(step==1&&ready){Check(progress.Maximum>1000,"duration invalid");Check(cues.Count>200,"subtitle count invalid");checks.Add("native decode opened; duration="+progress.Maximum+"; cues="+cues.Count);if(cues[0].Words.Count>0){Seek(cues[0].Words[0].Start+0.02);Check(litWord==0,"word highlight missing");caption.SelectAll();string selected=caption.Selection.Text;Tick();Check(selected.Length>0&&caption.Selection.Text==selected,"selection was lost during timer tick");caption.RaiseEvent(new MouseButtonEventArgs(Mouse.PrimaryDevice,Environment.TickCount,MouseButton.Left){RoutedEvent=Mouse.MouseUpEvent});subtitleArea.RaiseEvent(new MouseButtonEventArgs(Mouse.PrimaryDevice,Environment.TickCount,MouseButton.Left){RoutedEvent=Mouse.MouseUpEvent});Check(visible,"caption/blank click hid subtitles");caption.Selection.Select(caption.Document.ContentStart,caption.Document.ContentStart);checks.Add("JSON acoustic highlight, stable selection and non-hiding caption/blank clicks passed");}Seek(15);TogglePlay();from=15;step++;}
    else if(step==2&&media.Position.TotalSeconds>from+0.15){checks.Add("playback advances");TogglePlay();Seek(70);Check(Math.Abs(media.Position.TotalSeconds-70)<0.2,"seek failed");MoveCue(1);Check(playing,"next cue did not play");ToggleSubtitles();Check(!visible,"subtitle toggle failed");MoveCue(1);Check(!visible,"navigation revealed hidden subtitle");ToggleSubtitles();rate.SelectedIndex=2;Check(media.SpeedRatio==1.25,"speed failed");volume.Value=0.4;Check(Math.Abs(media.Volume-0.4)<0.01,"volume failed");checks.Add("seek, next sentence, hidden subtitles, speed and volume passed");loop=true;loopIndex=3;Seek(cues[3].End-0.1);loopIndex=3;step++;}
    else if(step==3&&loopReturns>0){Check(loopIndex==3,"loop target changed");checks.Add("sentence loop returned to start");loop=false;autoPause=true;Seek(cues[4].End-0.15);step++;}
    else if(step==4&&!playing){Check(pausedCue==4,"sentence end pause failed");checks.Add("sentence end auto pause passed");TogglePlay();Check(media.Position.TotalSeconds>=cues[5].Start-0.05,"resume did not advance to next sentence");checks.Add("resume next sentence passed");finish(null);}
   }catch(Exception ex){finish(ex);}};test.Start();
  }
  [STAThread] public static int Main(string[] args){if(args.Length>0&&args[0]=="--test-srt"){try{var c=Subtitles.Read(args[1]);File.WriteAllText(args[2],"PASS cues="+c.Count+" first="+c[0].Text);return 0;}catch(Exception ex){File.WriteAllText(args[2],"FAIL "+ex.Message);return 1;}}var app=new Application();if(args.Length==4&&args[0]=="--smoke"){var p=new Player(new string[0],false);p.Loaded+=(s,e)=>p.Smoke(args[1],args[2],args[3]);app.Run(p);}else app.Run(new Player(args));return 0;}
 }
}
